"""AI provider registry: credentials (encrypted), models & pricing, connection tests, health.

Credential handling is delegated to :class:`app.services.credentials.CredentialService`; this
module only maps HTTP to it. No response schema has a field that can carry a secret.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.youtube import build_youtube_service
from app.api.deps import Principal, get_principal, require_role, write_audit
from app.container import ProviderFactory
from app.core.crypto import master_key_status
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.db.session import get_session
from app.models import AgentConfiguration, AiProvider
from app.schemas import (
    ProviderCreate,
    ProviderOut,
    ProviderTestResult,
    ProviderUpdate,
)
from app.services.credentials import CredentialService, assert_valid_secret, invalidate

router = APIRouter(prefix="/providers", tags=["providers"])

COMPATIBLE_LLM = {"openai-compatible", "anthropic-compatible"}

SUPPORTED = {
    "llm": {"openai", "gemini", "openai-compatible", "anthropic-compatible", "mock"},
    "tts": {"cartesia", "elevenlabs", "mock"},
    "image": {"openai", "openai-compatible", "gemini", "mock"},
    "youtube": {"google", "mock"},
}

_KIND_PORTS = {"llm": "LLM", "tts": "TTS", "image": "IMAGE", "video": "VIDEO", "youtube": "YOUTUBE"}


def _out(p: AiProvider) -> ProviderOut:
    return ProviderOut(
        id=p.id,
        kind=p.kind,
        slug=p.slug,
        name=p.name,
        vendor=p.vendor,
        base_url=p.base_url,
        models=list(p.models or []),
        credential_fingerprint=p.credential_fingerprint,
        has_credential=bool(p.credential_ciphertext),
        credential_status=p.credential_status or ("active" if p.credential_ciphertext else "unset"),
        credential_version=int(p.credential_version or 0),
        credential_updated_at=p.credential_updated_at,
        is_enabled=p.is_enabled,
        is_mock=p.is_mock,
        priority=int(p.priority or 100),
        health=p.health,
        health_detail=p.health_detail,
        health_checked_at=p.health_checked_at,
        extra_config=dict(p.extra_config or {}),
        created_at=p.created_at,
    )


async def _get(session: AsyncSession, principal: Principal, provider_id: uuid.UUID) -> AiProvider:
    p = await session.scalar(
        select(AiProvider).where(
            AiProvider.id == provider_id, AiProvider.workspace_id == principal.workspace.id
        )
    )
    if p is None:
        raise NotFoundError("Provider not found")
    return p


async def _get_by_slug(session: AsyncSession, principal: Principal, kind: str, slug: str) -> AiProvider:
    p = await session.scalar(
        select(AiProvider).where(
            AiProvider.workspace_id == principal.workspace.id,
            AiProvider.kind == kind,
            AiProvider.slug == slug,
        )
    )
    if p is None:
        raise NotFoundError(f"{kind} provider '{slug}' is not registered")
    return p


@router.get("", response_model=list[ProviderOut])
async def list_providers(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderOut]:
    rows = (
        await session.execute(
            select(AiProvider)
            .where(AiProvider.workspace_id == principal.workspace.id)
            .order_by(AiProvider.kind, AiProvider.priority, AiProvider.created_at)
        )
    ).scalars()
    return [_out(p) for p in rows]


@router.get("/adapters")
async def adapters() -> dict[str, list[str]]:
    return {kind: sorted(slugs) for kind, slugs in SUPPORTED.items()}


@router.get("/encryption")
async def encryption_status() -> dict[str, Any]:
    """Explicit master-key state — the UI refuses credential writes when this is not ready."""
    ready, problem = master_key_status()
    return {"ready": ready, "problem": problem, "algorithm": "AES-256-GCM"}


@router.post("", response_model=ProviderOut, status_code=201)
async def create_provider(
    payload: ProviderCreate,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> ProviderOut:
    if payload.slug.startswith("mock") and not payload.slug == "mock":
        raise ValidationAppError("Only the 'mock' adapter is available for development")
    if payload.slug not in SUPPORTED.get(payload.kind, set()):
        raise ValidationAppError(
            f"Adapter '{payload.slug}' is not supported for {payload.kind}. "
            f"Choose one of: {', '.join(sorted(SUPPORTED.get(payload.kind, [])))}"
        )
    exists = await session.scalar(
        select(AiProvider.id).where(
            AiProvider.workspace_id == principal.workspace.id,
            AiProvider.slug == payload.slug,
            AiProvider.kind == payload.kind,
        )
    )
    if exists:
        raise ConflictError(f"{payload.kind} provider '{payload.slug}' already exists")
    if payload.slug in COMPATIBLE_LLM and not (payload.base_url or "").strip():
        raise ValidationAppError(
            f"'{payload.slug}' needs a base URL (for example https://api.groq.com/openai/v1)"
        )
    if payload.kind == "image" and payload.slug == "openai-compatible" and not (
        payload.base_url or ""
    ).strip():
        raise ValidationAppError(
            "An OpenAI-compatible image provider needs a base URL ending in /v1 "
            "(for example https://gateway.example.com/v1)"
        )
    is_mock = payload.slug == "mock"
    provider = AiProvider(
        workspace_id=principal.workspace.id,
        kind=payload.kind,
        slug=payload.slug,
        name=payload.name,
        vendor=payload.vendor,
        base_url=payload.base_url,
        models=[m.model_dump(exclude_none=True) for m in payload.models],
        extra_config=payload.extra_config,
        priority=payload.priority,
        is_mock=is_mock,
        health="ok" if is_mock else "unknown",
        health_detail="Mock adapter" if is_mock else None,
        health_checked_at=datetime.now(UTC) if is_mock else None,
        credential_status="unset" if not payload.api_key else "active",
    )
    session.add(provider)
    await session.flush()
    if payload.api_key and not is_mock:
        assert_valid_secret(payload.slug, payload.api_key)
        await CredentialService(session).set_credentials(
            provider, {"api_key": payload.api_key}, actor_id=principal.user.id,
            action="provider.credentials.created",
        )
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="provider.created", target_type="provider", target_id=str(provider.id),
                      request=request, kind=payload.kind, slug=payload.slug)
    await session.commit()
    return _out(provider)


@router.get("/{provider_id}", response_model=ProviderOut)
async def get_provider(
    provider_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> ProviderOut:
    return _out(await _get(session, principal, provider_id))


@router.patch("/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: uuid.UUID,
    payload: ProviderUpdate,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> ProviderOut:
    provider = await _get(session, principal, provider_id)
    data = payload.model_dump(exclude_unset=True)
    api_key = data.pop("api_key", None)
    for field, value in data.items():
        if value is not None:
            setattr(provider, field, value)
    if data.get("base_url") is None and "base_url" in data:
        provider.base_url = None
    if api_key and not provider.is_mock:
        # Empty strings arrive as None from the form; guard again so a blank field never clears.
        if str(api_key).strip():
            assert_valid_secret(provider.slug, str(api_key).strip())
            await CredentialService(session).set_credentials(
                provider, {"api_key": api_key}, actor_id=principal.user.id
            )
    if "is_enabled" in data or "base_url" in data:
        provider.health = "unknown"
        invalidate(provider.id)
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="provider.updated", target_type="provider", target_id=str(provider.id),
                      request=request, fields=list(data))
    await session.commit()
    return _out(provider)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove a provider for real.

    Credentials are shredded and the row is deleted. Agent bindings are cleared first (they fall
    back to the workspace default), and historical usage/audit rows are kept because they are
    immutable records — their ``provider_id`` is set to NULL by the schema, the fingerprint and
    slug in the audit log still identify what ran.
    """
    provider = await _get(session, principal, provider_id)
    slug, kind = provider.slug, provider.kind
    await session.execute(
        AgentConfiguration.__table__.update()
        .where(AgentConfiguration.provider_id == provider.id)
        .values(provider_id=None)
    )
    await session.execute(
        AgentConfiguration.__table__.update()
        .where(AgentConfiguration.fallback_provider_id == provider.id)
        .values(fallback_provider_id=None)
    )
    invalidate(provider.id)
    await session.delete(provider)
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="provider.deleted", target_type="provider", target_id=str(provider_id),
                      request=request, slug=slug, kind=kind)
    await session.commit()


# --------------------------------------------------------------------------- credentials


class CredentialIn(BaseModel):
    api_key: str = Field(default="", max_length=500, description="New key. Empty values are ignored.")
    default_model: str | None = Field(default=None, max_length=120)
    default_voice_id: str | None = Field(default=None, max_length=160)
    default_output_format: str | None = Field(default=None, max_length=64)


class CredentialOut(BaseModel):
    provider: str
    kind: str
    has_credential: bool
    status: str
    version: int
    fingerprint: str | None
    updated_at: datetime | None
    fields: list[str]
    readable: bool
    problem: str | None
    encryption_ready: bool


async def _credential_out(session: AsyncSession, provider: AiProvider) -> CredentialOut:
    state = await CredentialService(session).state(provider)
    ready, _ = master_key_status()
    return CredentialOut(
        provider=provider.slug,
        kind=provider.kind,
        has_credential=state.has_credential,
        status=state.status,
        version=state.version,
        fingerprint=state.fingerprint,
        updated_at=state.updated_at,
        fields=state.fields,
        readable=state.readable,
        problem=state.problem,
        encryption_ready=ready,
    )


async def _apply_defaults(provider: AiProvider, payload: CredentialIn, session: AsyncSession) -> None:
    extra = dict(provider.extra_config or {})
    changed = False
    for field, key in (("default_model", "default_model"),
                       ("default_voice_id", "default_voice_id"),
                       ("default_output_format", "default_output_format")):
        value = getattr(payload, field)
        if value is None:
            continue
        extra[key] = value.strip() or None
        changed = True
    if changed:
        provider.extra_config = {k: v for k, v in extra.items() if v not in (None, "")}
        await session.flush()


@router.get("/{kind}/{slug}/credentials", response_model=CredentialOut)
async def get_credentials(
    kind: Literal["llm", "tts", "image", "youtube"],
    slug: str,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> CredentialOut:
    provider = await _get_by_slug(session, principal, kind, slug)
    return await _credential_out(session, provider)


@router.post("/{kind}/{slug}/credentials", response_model=CredentialOut)
async def set_credentials(
    kind: Literal["llm", "tts", "image", "youtube"],
    slug: str,
    payload: CredentialIn,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> CredentialOut:
    provider = await _get_by_slug(session, principal, kind, slug)
    if provider.is_mock:
        raise ValidationAppError("The mock adapter does not use credentials")
    if master_key_status()[0] is False:
        raise ValidationAppError(
            "APP_ENCRYPTION_KEY is not configured — credentials cannot be stored safely. "
            "Set a 32-byte key and restart the API once."
        )
    if payload.api_key.strip():
        assert_valid_secret(provider.slug, payload.api_key.strip())
    await _apply_defaults(provider, payload, session)
    await CredentialService(session).set_credentials(
        provider, {"api_key": payload.api_key}, actor_id=principal.user.id
    )
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="provider.credentials.updated", target_type="provider_credential",
                      target_id=str(provider.id), request=request, provider=provider.slug)
    await session.commit()
    return await _credential_out(session, provider)


@router.put("/{kind}/{slug}/credentials", response_model=CredentialOut)
async def replace_credentials(
    kind: Literal["llm", "tts", "image", "youtube"],
    slug: str,
    payload: CredentialIn,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> CredentialOut:
    """Same semantics as POST but requires a non-empty key (explicit rotation)."""
    if not payload.api_key.strip():
        raise ValidationAppError("Provide the new key to rotate it")
    return await set_credentials(kind, slug, payload, request, principal, session)


@router.delete("/{kind}/{slug}/credentials", response_model=CredentialOut)
async def remove_credentials(
    kind: Literal["llm", "tts", "image", "youtube"],
    slug: str,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> CredentialOut:
    """Disable the credential: the secret is shredded, the provider row and its history remain."""
    provider = await _get_by_slug(session, principal, kind, slug)
    await CredentialService(session).disable(
        provider, actor_id=principal.user.id, reason="Removed from the providers screen"
    )
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="provider.credentials.removed", target_type="provider_credential",
                      target_id=str(provider.id), request=request, provider=provider.slug)
    await session.commit()
    return await _credential_out(session, provider)


# --------------------------------------------------------------------------- google oauth client


class GoogleClientIn(BaseModel):
    client_id: str = Field(min_length=10, max_length=300,
                           description="OAuth client id, e.g. 123-abc.apps.googleusercontent.com")
    client_secret: str = Field(default="", max_length=300,
                               description="Leave empty to keep the stored secret while changing the id")


class GoogleClientOut(BaseModel):
    configured: bool
    source: str | None  # "dashboard" | "environment" | None
    client_id_masked: str | None
    has_secret: bool
    secret_updated_at: datetime | None
    env_fallback: bool
    redirect_uri: str


def _mask_client_id(value: str | None) -> str | None:
    if not value:
        return None
    return value if len(value) <= 24 else f"{value[:12]}...{value[-24:]}"


async def _google_client_out(session: AsyncSession, workspace_id: uuid.UUID) -> GoogleClientOut:
    from app.core.settings import get_settings
    from app.services.google_credentials import resolve_google_client

    settings = get_settings()
    env_fallback = bool(settings.google_client_id and settings.google_client_secret)
    provider = await session.scalar(
        select(AiProvider).where(
            AiProvider.workspace_id == workspace_id,
            AiProvider.kind == "youtube",
            AiProvider.slug == "google",
        )
    )
    stored_id: str | None = None
    has_secret = False
    updated_at: datetime | None = None
    if provider is not None and provider.credential_ciphertext:
        service = CredentialService(session)
        state = await service.state(provider)
        if state.readable:
            data = await service.get_credentials(provider)
            stored_id = data.get("client_id")
            has_secret = bool(data.get("client_secret"))
            updated_at = provider.credential_updated_at
    client = await resolve_google_client(session, workspace_id)
    return GoogleClientOut(
        configured=client is not None,
        source=client.source if client else None,
        client_id_masked=_mask_client_id(
            stored_id or (settings.google_client_id if env_fallback else None)
        ),
        has_secret=has_secret,
        secret_updated_at=updated_at,
        env_fallback=env_fallback,
        redirect_uri=settings.google_oauth_redirect,
    )


@router.get("/youtube/google/client", response_model=GoogleClientOut)
async def get_google_client(
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> GoogleClientOut:
    """Which Google OAuth client will be used. Never returns the secret."""
    return await _google_client_out(session, principal.workspace.id)


@router.put("/youtube/google/client", response_model=GoogleClientOut)
async def set_google_client(
    payload: GoogleClientIn,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> GoogleClientOut:
    """Store the Google OAuth client from the dashboard (encrypted at rest)."""
    from app.services.google_credentials import save_google_client

    if master_key_status()[0] is False:
        raise ValidationAppError(
            "APP_ENCRYPTION_KEY is not configured - credentials cannot be stored safely."
        )
    client_id = payload.client_id.strip()
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise ValidationAppError(
            "A Google OAuth client id ends with .apps.googleusercontent.com"
        )
    secret = payload.client_secret.strip()
    if secret and len(secret) < 8:
        raise ValidationAppError("The client secret looks too short")
    provider = await save_google_client(session, principal.workspace.id, client_id, secret or None)
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="youtube.client.updated", target_type="provider",
                      target_id=str(provider.id), request=request, secret_changed=bool(secret))
    await session.commit()
    return await _google_client_out(session, principal.workspace.id)


@router.delete("/youtube/google/client", status_code=204)
async def clear_google_client(
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove the dashboard client; the environment fallback (if any) takes over again."""
    provider = await session.scalar(
        select(AiProvider).where(
            AiProvider.workspace_id == principal.workspace.id,
            AiProvider.kind == "youtube",
            AiProvider.slug == "google",
        )
    )
    if provider is not None and provider.credential_ciphertext:
        await CredentialService(session).disable(
            provider, actor_id=principal.user.id, reason="Google OAuth client removed"
        )
        await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                          action="youtube.client.removed", target_type="provider",
                          target_id=str(provider.id), request=request)
        await session.commit()


# --------------------------------------------------------------------------- tests / health


@router.post("/{provider_id}/test", response_model=ProviderTestResult)
async def test_provider(
    provider_id: uuid.UUID,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> ProviderTestResult:
    provider = await _get(session, principal, provider_id)
    factory = ProviderFactory(session)
    ok, detail, checks = False, "", []
    if provider.kind == "video":
        # The only video engine is Remotion; report Node, the package versions and the bundle.
        from app.services.render import engine_status

        status = await asyncio.to_thread(engine_status)
        ok, detail = status["ok"], status["detail"]
        checks = [
            {"name": "node", "ok": bool(status["node"]), "detail": status["node"] or "not found"},
            {"name": "remotion", "ok": bool(status["remotion"]), "detail": status["remotion"] or "not installed"},
            {"name": "engine", "ok": status["ok"], "detail": detail},
        ]
        provider.health = "ok" if ok else "error"
        provider.health_detail = detail[:400]
        provider.health_checked_at = datetime.now(UTC)
        await session.commit()
        return ProviderTestResult(ok=ok, detail=detail, checked_at=provider.health_checked_at,
                                  checks=checks)
    try:
        adapter = await factory.build(provider)
        if provider.kind == "tts" and not provider.is_mock:
            result = await adapter.test_connection()
            ok, detail, checks = result.ok, result.detail, result.checks
        elif provider.kind == "youtube" and provider.slug == "google":
            from app.services.google_credentials import resolve_google_client

            client = await resolve_google_client(session, principal.workspace.id)
            ok = client is not None
            detail = (
                f"Google OAuth client configured ({client.source}) · connect channels individually"
                if client
                else "Add the OAuth client id and secret here, or set GOOGLE_CLIENT_ID / "
                     "GOOGLE_CLIENT_SECRET"
            )
            checks = [
                {"name": "client", "ok": client is not None,
                 "detail": client.source if client else "missing"},
            ]
        else:
            ok, detail = await adapter.health()
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, _safe_error(exc)
    provider.health = "ok" if ok else "error"
    provider.health_detail = detail[:400]
    provider.health_checked_at = datetime.now(UTC)
    await session.commit()
    return ProviderTestResult(ok=ok, detail=detail, checked_at=provider.health_checked_at,
                              checks=checks)


def _safe_error(exc: Exception) -> str:
    from app.ports.tts import TTSError

    if isinstance(exc, TTSError):
        return exc.message
    return f"{type(exc).__name__}: {exc}"


@router.get("/health")
async def provider_health(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (
        await session.execute(
            select(AiProvider).where(AiProvider.workspace_id == principal.workspace.id)
        )
    ).scalars()
    return [
        {"id": str(p.id), "name": p.name, "kind": p.kind, "health": p.health,
         "detail": p.health_detail, "checked_at": p.health_checked_at, "is_mock": p.is_mock}
        for p in rows
    ]


class DiscoverModelsIn(BaseModel):
    slug: Literal["openai-compatible", "anthropic-compatible"]
    base_url: str = Field(min_length=8, max_length=500)
    api_key: str = Field(min_length=4, max_length=400)


@router.post("/discover-models")
async def discover_models(
    payload: DiscoverModelsIn,
    principal: Principal = Depends(require_role("editor")),
) -> dict[str, Any]:
    """List the models an endpoint exposes — before the provider is saved.

    Uses the credential the operator just typed (never stored) so the add-provider form can fill in
    the model list from the provider itself instead of asking them to type identifiers from memory.
    """
    from app.adapters.llm import build_llm_provider

    try:
        provider = build_llm_provider(payload.slug, payload.api_key, payload.base_url)
        models = await provider.list_models(refresh=True)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 - a discovery failure is a normal, expected outcome
        return {"models": [], "error": f"{type(exc).__name__}: {exc}"}
    return {"models": models, "error": None if models else "This endpoint published no model list."}


@router.get("/{provider_id}/models")
async def provider_models(
    provider_id: uuid.UUID,
    refresh: bool = False,
    persist: bool = False,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Models exposed by a provider.

    For OpenAI/Anthropic-compatible endpoints this queries the endpoint's own ``/models`` route, so
    operators see exactly what their server offers (and custom gateways work without code changes).
    ``persist=true`` stores the discovered list on the provider row so the agent configurator can
    offer it in a dropdown without another round trip.
    """
    provider = await _get(session, principal, provider_id)
    adapter = await ProviderFactory(session).build(provider)
    discovered: list[dict[str, Any]] = []
    try:
        lister = getattr(adapter, "list_models", None)
        if lister is not None:
            discovered = await lister(refresh=refresh)
    except Exception as exc:  # noqa: BLE001 - surface as a readable error, never a 500
        return {"discovered": False, "models": list(provider.models or []),
                "error": f"{type(exc).__name__}: {exc}"}
    if not discovered:
        return {"discovered": False, "models": list(provider.models or [])}
    if persist:
        merged = {m.get("id"): m for m in provider.models or []}
        for model in discovered:
            current = merged.get(model["id"], {})
            merged[model["id"]] = {**current, **model}
        provider.models = list(merged.values())
        await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                          action="provider.models.synced", target_type="provider",
                          target_id=str(provider.id), count=len(discovered))
        await session.commit()
    return {"discovered": True, "models": discovered}


@router.get("/voices/{provider_id}")
async def voices(
    provider_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    provider = await _get(session, principal, provider_id)
    if provider.kind != "tts":
        raise ValidationAppError("Not a TTS provider")
    adapter = await ProviderFactory(session).build(provider)
    rows = await adapter.list_voices()
    return [
        {"id": v.voice_id, "name": v.name, "language": v.language, "description": v.description,
         "preview_url": v.preview_url, "labels": v.labels}
        for v in rows
    ]


__all__ = ["router", "build_youtube_service"]
