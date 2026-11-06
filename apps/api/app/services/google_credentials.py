"""Resolve the Google OAuth client used for YouTube publishing.

The client id/secret can come from two places, in this order:

1. **The dashboard** — the ``youtube / google`` provider row stores both values encrypted in the
   credential vault (same AES-256-GCM path as every other provider). This is what operators set in
   *Providers → YouTube → manage key*, and it takes effect immediately.
2. **The environment** — ``GOOGLE_CLIENT_ID`` / ``GOOGLE_CLIENT_SECRET``. Kept working so existing
   deployments do not have to re-enter anything.

Returning a single object keeps the OAuth flow free of ``get_settings()`` calls scattered around, and
makes "is OAuth configured?" answerable with one lookup.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import CredentialError, get_vault
from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models import AiProvider
from app.services.credentials import CredentialService

log = get_logger("factory.youtube.oauth")

#: Field names inside the encrypted blob for the youtube/google provider row.
CLIENT_ID_FIELD = "client_id"
CLIENT_SECRET_FIELD = "client_secret"


@dataclass(slots=True)
class GoogleOAuthClient:
    client_id: str
    client_secret: str
    source: str  # "dashboard" | "environment"

    @property
    def ready(self) -> bool:
        return bool(self.client_id and self.client_secret)


async def resolve_google_client(
    session: AsyncSession, workspace_id: uuid.UUID | None = None
) -> GoogleOAuthClient | None:
    """Dashboard credentials first, then the environment. ``None`` when neither is usable."""
    query = select(AiProvider).where(
        AiProvider.kind == "youtube", AiProvider.slug == "google", AiProvider.is_mock.is_(False)
    )
    if workspace_id is not None:
        query = query.where(AiProvider.workspace_id == workspace_id)
    provider = await session.scalar(query.order_by(AiProvider.created_at).limit(1))
    if provider is not None and provider.credential_ciphertext:
        try:
            data = get_vault().open(provider.credential_ciphertext, aad=_aad(provider))
            client_id = (data.get(CLIENT_ID_FIELD) or "").strip()
            client_secret = (data.get(CLIENT_SECRET_FIELD) or "").strip()
        except CredentialError as exc:
            # A vault problem must not silently fall back to env: that would publish with a
            # different client than the operator thinks.
            log.warning("google.oauth_unreadable provider=%s error=%s", provider.id, exc)
            return None
        if client_id and client_secret:
            return GoogleOAuthClient(client_id, client_secret, "dashboard")

    settings = get_settings()
    env_id = (settings.google_client_id or "").strip()
    env_secret = (settings.google_client_secret or "").strip()
    if env_id and env_secret:
        return GoogleOAuthClient(env_id, env_secret, "environment")
    return None


async def save_google_client(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    client_id: str,
    client_secret: str | None,
) -> AiProvider:
    """Store the client id and (optionally) a new secret on the youtube/google provider row.

    ``client_secret`` may be ``None`` to keep the stored secret while changing the id — that is how
    the dashboard form behaves when the operator only edits the id.
    """
    provider = await session.scalar(
        select(AiProvider).where(
            AiProvider.workspace_id == workspace_id,
            AiProvider.kind == "youtube",
            AiProvider.slug == "google",
        )
    )
    if provider is None:
        provider = AiProvider(
            workspace_id=workspace_id,
            kind="youtube",
            slug="google",
            name="YouTube (Google OAuth)",
            vendor="Google",
            is_mock=False,
            is_enabled=True,
            health="unknown",
        )
        session.add(provider)
        await session.flush()

    existing: dict[str, str] = {}
    if provider.credential_ciphertext:
        try:
            # Read through the service so the in-process cache is consulted, not bypassed.
            existing = await CredentialService(session).get_credentials(provider)
        except CredentialError:
            existing = {}
    values = {"client_id": client_id.strip()}
    if client_secret:
        values["client_secret"] = client_secret.strip()
    elif existing.get("client_secret"):
        # Keep the stored secret: CredentialService.merge only replaces what is non-empty.
        values["client_secret"] = existing["client_secret"]
    await CredentialService(session).set_credentials(
        provider, values, action="youtube.client.updated"
    )
    await session.flush()
    return provider


def _aad(provider: AiProvider) -> str:
    # Local import keeps this module importable without pulling the whole services package.
    from app.services.credentials import aad_for

    return aad_for(provider)
