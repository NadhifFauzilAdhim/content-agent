"""Centralised provider credential management.

One service owns the whole credential lifecycle so every integration (TTS, LLM, images, YouTube)
gets identical guarantees — no per-provider credential code:

* **At rest** — AES-256-GCM via :class:`CredentialVault`, bound to the provider row. A missing or
  invalid master key raises instead of falling back to plaintext.
* **Reads** — cached in-process for a short TTL (so an unchanged key is not decrypted on every
  generation). Any write bumps ``credential_version``, replaces the cache entry and invalidates
  the TTL, so changes take effect immediately without restarting the application.
* **Writes** — ``set_credentials`` merges: an empty value never overwrites an existing secret.
  Every change appends an audit row containing only field names and fingerprints.
* **Exposure** — the API can only see :func:`mask`, which returns a fingerprint, never the value.
* **Removal** — ``disable`` wipes the ciphertext (shredding the key), keeps the row, and records
  who did it and why.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import CredentialError, CredentialVault, get_vault, master_key_status
from app.core.errors import ConflictError, ValidationAppError
from app.core.logging import get_logger
from app.models import AiProvider

log = get_logger("factory.credentials")

CACHE_TTL_SECONDS = 60.0

#: Fields that may be rotated for a provider. Values are merged, so partial updates are safe.
SECRET_FIELDS = ("api_key",)


@dataclass(slots=True)
class _CacheEntry:
    data: dict[str, str]
    version: int
    expires: float


_CACHE: dict[str, _CacheEntry] = {}


def aad_for(provider: AiProvider) -> str:
    """Binds a ciphertext to one provider row in one workspace."""
    return f"provider:{provider.workspace_id}:{provider.id}"


@dataclass(slots=True)
class CredentialState:
    has_credential: bool
    status: str
    version: int
    fingerprint: str | None
    updated_at: datetime | None
    readable: bool
    problem: str | None = None
    fields: list[str] = field(default_factory=list)


class CredentialService:
    def __init__(self, session: AsyncSession, vault: CredentialVault | None = None) -> None:
        self.session = session
        self._vault = vault

    # -- vault -------------------------------------------------------------
    def _get_vault(self) -> CredentialVault:
        if self._vault is None:
            ready, problem = master_key_status()
            if not ready:
                raise CredentialError(problem or "Encryption key unavailable", code="master_key_missing")
            self._vault = get_vault()
        return self._vault

    # -- read --------------------------------------------------------------
    async def get_credentials(
        self, provider: AiProvider, *, expected_version: int | None = None
    ) -> dict[str, str]:
        """Decrypted secrets for adapter use only. Never serialise the result."""
        if provider.is_mock:
            return {}
        if not provider.credential_ciphertext:
            return {}
        key = str(provider.id)
        cached = _CACHE.get(key)
        if cached and cached.expires > time.monotonic():
            if expected_version is None or cached.version == expected_version:
                return dict(cached.data)
        vault = self._get_vault()
        data = vault.open(provider.credential_ciphertext, aad=aad_for(provider))
        if vault.is_legacy(provider.credential_ciphertext):
            # Re-seal legacy Fernet payloads with AES-256-GCM on first read.
            provider.credential_ciphertext = vault.seal(data, aad=aad_for(provider))
            await self.session.flush()
        _CACHE[key] = _CacheEntry(dict(data), int(provider.credential_version or 0),
                                  time.monotonic() + CACHE_TTL_SECONDS)
        if expected_version is not None and int(provider.credential_version or 0) != expected_version:
            log.info("credentials.version_changed provider=%s pinned=%s current=%s", provider.id,
                     expected_version, provider.credential_version)
        return dict(data)

    async def get_secret(self, provider: AiProvider, name: str = "api_key",
                         *, expected_version: int | None = None) -> str | None:
        data = await self.get_credentials(provider, expected_version=expected_version)
        value = data.get(name)
        return value or None

    async def state(self, provider: AiProvider) -> CredentialState:
        ready, problem = master_key_status()
        readable = True
        fields_list: list[str] = []
        if provider.credential_ciphertext and ready:
            try:
                fields_list = sorted((await self.get_credentials(provider)).keys())
            except CredentialError as exc:
                readable = False
                problem = str(exc)
        return CredentialState(
            has_credential=bool(provider.credential_ciphertext),
            status=provider.credential_status or ("active" if provider.credential_ciphertext else "unset"),
            version=int(provider.credential_version or 0),
            fingerprint=provider.credential_fingerprint,
            updated_at=provider.credential_updated_at,
            readable=readable,
            problem=problem,
            fields=fields_list,
        )

    # -- write -------------------------------------------------------------
    async def set_credentials(
        self,
        provider: AiProvider,
        values: dict[str, Any],
        *,
        actor_id: uuid.UUID | None = None,
        action: str = "provider.credentials.updated",
    ) -> CredentialState:
        """Merge secrets. Empty/None values are ignored so a blank form cannot erase a key."""
        ready, problem = master_key_status()
        if not ready:
            raise ConflictError(problem or "Encryption key is not configured")
        cleaned = {
            name: str(value).strip()
            for name, value in values.items()
            if name in SECRET_FIELDS and value is not None and str(value).strip()
        }
        if not cleaned:
            return await self.state(provider)
        vault = self._get_vault()
        existing: dict[str, str] = {}
        if provider.credential_ciphertext:
            try:
                existing = await self.get_credentials(provider)
            except CredentialError:
                # Unreadable with this key: a deliberate rotation replaces it wholesale.
                existing = {}
        merged = {**existing, **cleaned}
        provider.credential_ciphertext = vault.seal(merged, aad=aad_for(provider))
        provider.credential_fingerprint = vault.fingerprint(merged["api_key"])
        provider.credential_version = int(provider.credential_version or 0) + 1
        provider.credential_status = "active"
        provider.credential_updated_at = datetime.now(UTC)
        provider.health = "unknown"
        provider.health_detail = None
        _CACHE[str(provider.id)] = _CacheEntry(dict(merged), provider.credential_version,
                                               time.monotonic() + CACHE_TTL_SECONDS)
        from app.api.deps import write_audit

        await write_audit(
            self.session,
            workspace_id=provider.workspace_id,
            actor_id=actor_id,
            action=action,
            target_type="provider_credential",
            target_id=str(provider.id),
            provider=provider.slug,
            fields=sorted(cleaned),
            fingerprint=provider.credential_fingerprint,
            version=provider.credential_version,
        )
        await self.session.flush()
        return await self.state(provider)

    async def disable(
        self,
        provider: AiProvider,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> CredentialState:
        """Shred the stored secret but keep the provider row and its history."""
        provider.credential_ciphertext = None
        provider.credential_fingerprint = None
        provider.credential_version = int(provider.credential_version or 0) + 1
        provider.credential_status = "disabled"
        provider.credential_updated_at = datetime.now(UTC)
        provider.health = "unknown"
        provider.health_detail = "Credential removed — add a key to use this provider"
        invalidate(provider.id)
        from app.api.deps import write_audit

        await write_audit(
            self.session,
            workspace_id=provider.workspace_id,
            actor_id=actor_id,
            action="provider.credentials.removed",
            target_type="provider_credential",
            target_id=str(provider.id),
            provider=provider.slug,
            reason=reason,
            version=provider.credential_version,
        )
        await self.session.flush()
        return await self.state(provider)

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def mask(secret: str | None) -> str | None:
        """Display-safe representation; the full value is never returned."""
        if not secret:
            return None
        try:
            return CredentialVault.fingerprint(secret)
        except Exception:  # noqa: BLE001 - display must never fail a request
            return "••••"


def invalidate(provider_id: uuid.UUID | str) -> None:
    _CACHE.pop(str(provider_id), None)


def invalidate_all() -> None:
    _CACHE.clear()


async def provider_by_id(
    session: AsyncSession, workspace_id: uuid.UUID, provider_id: uuid.UUID
) -> AiProvider | None:
    return await session.scalar(
        select(AiProvider).where(
            AiProvider.id == provider_id, AiProvider.workspace_id == workspace_id
        )
    )


def validate_secret_format(slug: str, value: str) -> str | None:
    """Cheap sanity check for obviously wrong pastes (no provider-specific validation)."""
    if len(value) < 8:
        return "The key looks too short"
    if value != value.strip():
        return "The key has leading or trailing whitespace"
    if slug == "cartesia" and not value.startswith("sk_car_"):
        return "Cartesia keys start with sk_car_ — double-check the value"
    if any(ch.isspace() for ch in value):
        return "The key contains whitespace"
    return None


def assert_valid_secret(slug: str, value: str) -> None:
    problem = validate_secret_format(slug, value)
    if problem:
        raise ValidationAppError(problem)
