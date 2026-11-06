"""Text-to-speech API: provider catalogue, models, voices, previews, generation, comparison,
settings, and usage reporting.

Secrets never appear in any response: providers are described by flags, fingerprints and
capability metadata only.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_principal, require_role, write_audit
from app.core.crypto import master_key_status
from app.core.errors import NotFoundError, RateLimitedError, ValidationAppError
from app.core.logging import get_logger
from app.db.session import get_session
from app.models import AiProvider, TTSGeneration, TTSPreviewCache
from app.models.tts import TTSConfiguration
from app.ports.tts import (
    DialogueLine,
    TTSError,
    TTSInvalidRequestError,
    TTSTransientError,
)
from app.services import tts as tts_service
from app.services.credentials import invalidate  # noqa: F401  (re-exported for tests)

router = APIRouter(prefix="/tts", tags=["tts"])
log = get_logger("factory.api.tts")

MAX_TEXT = 200_000
PREVIEW_TTL = timedelta(hours=6)


# --------------------------------------------------------------------------- schemas


class VoiceSettings(BaseModel):
    model_config = {"extra": "allow"}
    stability: float | None = Field(default=None, ge=0, le=1)
    similarity_boost: float | None = Field(default=None, ge=0, le=1)
    style: float | None = Field(default=None, ge=0, le=1)
    speed: float | None = Field(default=None, ge=0.5, le=2.0)
    use_speaker_boost: bool | None = None
    volume: float | None = Field(default=None, ge=0.5, le=2.0)
    emotion: str | None = None


class SelectionIn(BaseModel):
    provider: str | None = None
    model: str | None = None
    voice_id: str | None = Field(default=None, max_length=160)
    language: str | None = Field(default=None, max_length=16)
    output_format: str | None = Field(default=None, max_length=64)
    voice_settings: dict[str, Any] = Field(default_factory=dict)


class GenerateIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    provider: str | None = None
    model: str | None = None
    voice_id: str | None = None
    language: str | None = None
    output_format: str | None = None
    voice_settings: dict[str, Any] = Field(default_factory=dict)
    channel_id: uuid.UUID | None = None
    workflow_id: uuid.UUID | None = None
    preserve_text: bool = True


class DialogueLineIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice_id: str = Field(min_length=1, max_length=160)
    speaker: str | None = None


class DialogueIn(BaseModel):
    provider: str | None = None
    model: str | None = None
    language: str | None = None
    output_format: str | None = None
    voice_settings: dict[str, Any] = Field(default_factory=dict)
    lines: list[DialogueLineIn] = Field(min_length=1, max_length=50)


class CompareSide(BaseModel):
    provider: str
    model: str | None = None
    voice_id: str | None = None
    output_format: str | None = None
    voice_settings: dict[str, Any] = Field(default_factory=dict)


class CompareIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    language: str = "en"
    left: CompareSide
    right: CompareSide


class SettingsIn(BaseModel):
    provider: str
    fallback_provider: str | None = None
    model: str | None = None
    voice_id: str | None = None
    language: str | None = None
    output_format: str | None = None
    voice_settings: dict[str, Any] = Field(default_factory=dict)


class ChannelVoiceIn(BaseModel):
    provider: str | None = None
    fallback_provider: str | None = None
    model: str | None = None
    voice_id: str | None = None
    language: str | None = None
    output_format: str | None = None
    voice_settings: dict[str, Any] = Field(default_factory=dict)
    clear: bool = False


class TestIn(BaseModel):
    provider: str
    model: str | None = None
    voice_id: str | None = None
    output_format: str | None = None
    language: str | None = None
    text: str = Field(default="The clock above the harbour struck six, and the town began to wake.",
                      max_length=600)


# --------------------------------------------------------------------------- helpers


def _tts_error(exc: TTSError) -> Exception:
    from app.core.errors import AppError, ConflictError, ProviderFailureError

    if isinstance(exc, TTSInvalidRequestError):
        return ValidationAppError(exc.message)
    if isinstance(exc, TTSTransientError):
        return ProviderFailureError(f"{exc.message} — retry in a moment or change provider.")
    if exc.code == "not_configured":
        return ConflictError(exc.message)
    return AppError(exc.message)


def _rate_bucket() -> dict[str, list[float]]:
    return {}


_BUCKETS: dict[str, list[float]] = _rate_bucket()


def _check_rate(key: str, limit: int) -> None:
    now = time.monotonic()
    window = [t for t in _BUCKETS.get(key, []) if now - t < 60]
    if len(window) >= limit:
        raise RateLimitedError(f"Generation rate limit reached ({limit}/min). Try again shortly.")
    window.append(now)
    _BUCKETS[key] = window


async def _synthesize_all(
    handler,  # type: ignore[no-untyped-def]
    items: list[Any],
    *,
    concurrency: int = 3,
) -> list[dict[str, Any]]:
    """Generate each item in parallel, isolated failures per item."""
    semaphore = asyncio.Semaphore(concurrency)

    async def run(item: Any) -> dict[str, Any]:
        async with semaphore:
            try:
                return await handler(item)
            except Exception as exc:  # noqa: BLE001 - per-item isolation
                return {"ok": False, "item": item, "error": getattr(exc, "message", str(exc))}

    return list(await asyncio.gather(*(run(i) for i in items)))


async def _provider_models(session: AsyncSession, workspace_id: uuid.UUID,
                           slug: str) -> list[dict[str, Any]]:
    from app.ports.tts import TTSError as _E
    from app.services.tts import TTSProviderFactory

    factory = TTSProviderFactory(session)
    try:
        handle = await factory.build(workspace_id, slug)
    except _E:
        return []
    infos = await handle.provider.list_models()
    return [
        {
            "id": i.id,
            "name": i.name,
            "description": i.description,
            "max_chars": i.max_chars,
            "languages": i.languages,
            "supports_dialogue": i.supports_dialogue,
            "deprecated": i.deprecated,
            "params": [asdict(p) for p in handle.provider.voice_params(i.id)],
            "output_formats": [
                {"id": f.id, "label": f.label, "container": f.container, "mime": f.mime,
                 "sample_rate": f.sample_rate, "bit_rate": f.bit_rate}
                for f in handle.provider.output_formats(i.id)
            ],
        }
        for i in infos
    ]


# --------------------------------------------------------------------------- catalogue


@router.get("/providers")
async def list_providers(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    from app.services.tts import TTSProviderFactory

    rows = await TTSProviderFactory(session).list_configured(principal.workspace.id)
    encrypted, problem = master_key_status()
    for row in rows:
        row["encryption_ready"] = encrypted
        row["encryption_problem"] = problem
    return rows


@router.get("/providers/{provider}")
async def provider_detail(
    provider: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from app.services.tts import TTSProviderFactory

    rows = await TTSProviderFactory(session).list_configured(principal.workspace.id)
    row = next((r for r in rows if r["slug"] == provider), None)
    if row is None:
        raise NotFoundError(f"TTS provider '{provider}' is not registered")
    row["models"] = await _provider_models(session, principal.workspace.id, provider)
    return row


@router.get("/models")
async def list_models(
    provider: str | None = None,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from app.services.tts import TTSProviderFactory

    rows = await TTSProviderFactory(session).list_configured(principal.workspace.id)
    slugs = [provider] if provider else [r["slug"] for r in rows if r["usable"] and not r["mock"]]
    models: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    async def load(slug: str) -> None:
        try:
            models[slug] = await _provider_models(session, principal.workspace.id, slug)
        except TTSError as exc:
            errors[slug] = exc.message

    await asyncio.gather(*(load(s) for s in slugs))
    return {"models": models, "errors": errors}


@router.get("/voices")
async def list_voices(
    provider: str | None = None,
    language: str | None = None,
    query: str | None = Query(default=None, max_length=120),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from app.services.tts import TTSProviderFactory

    rows = await TTSProviderFactory(session).list_configured(principal.workspace.id)
    slugs = [provider] if provider else [r["slug"] for r in rows if r["usable"]]
    cache_key = "|".join(slugs + [language or "", query or ""])
    if hasattr(router, "_voice_cache"):
        cached = router._voice_cache.get(cache_key)  # type: ignore[attr-defined]
        if cached and cached[0] > time.monotonic():
            return cached[1]
    out: dict[str, Any] = {"voices": {}, "errors": {}}
    factory = TTSProviderFactory(session)

    async def load(slug: str) -> None:
        try:
            handle = await factory.build(principal.workspace.id, slug)
            voices = await handle.provider.list_voices(language=language, query=query)
            out["voices"][slug] = [
                {
                    "voice_id": v.voice_id,
                    "name": v.name,
                    "language": v.language,
                    "locale": v.locale,
                    "gender": v.gender,
                    "category": v.category,
                    "description": v.description,
                    "labels": v.labels,
                    "own_voice": v.own_voice,
                    "has_preview": bool(v.preview_url),
                    "preview_endpoint": f"/api/v1/tts/voices/{slug}/{v.voice_id}/preview"
                    if v.preview_url else None,
                }
                for v in voices
            ]
        except TTSError as exc:
            out["errors"][slug] = exc.message
    await asyncio.gather(*(load(s) for s in slugs))
    if not hasattr(router, "_voice_cache"):
        router._voice_cache = {}  # type: ignore[attr-defined]
    if not out["errors"]:
        router._voice_cache[cache_key] = (time.monotonic() + 300, out)  # type: ignore[attr-defined]
    return out


@router.get("/voices/{provider}/{voice_id}/preview")
async def voice_preview(
    provider: str,
    voice_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    cached = await session.scalar(
        select(TTSPreviewCache).where(
            TTSPreviewCache.provider == provider, TTSPreviewCache.voice_id == voice_id
        )
    )
    if cached and cached.fetched_at and cached.fetched_at > datetime.now(UTC) - PREVIEW_TTL:
        return Response(cached.content, media_type=cached.mime, headers=_cache_headers())
    from app.services.tts import TTSProviderFactory

    handle = await TTSProviderFactory(session).build(principal.workspace.id, provider)
    voices = await handle.provider.list_voices()
    voice = next((v for v in voices if v.voice_id == voice_id), None)
    if voice is None or not voice.preview_url:
        raise NotFoundError("This voice has no preview")
    data = await handle.provider.voice_preview(voice)
    if not data:
        raise NotFoundError("Preview audio is unavailable right now")
    mime = "audio/wav" if data[:4] == b"RIFF" else "audio/mpeg"
    if cached:
        cached.content, cached.mime, cached.bytes = data, mime, len(data)
        cached.fetched_at = datetime.now(UTC)
    else:
        session.add(TTSPreviewCache(provider=provider, voice_id=voice_id, content=data,
                                    mime=mime, bytes=len(data)))
    await session.commit()
    return Response(data, media_type=mime, headers=_cache_headers())


def _cache_headers() -> dict[str, str]:
    return {"Cache-Control": "private, max-age=21600"}


# --------------------------------------------------------------------------- generation


@router.post("/generate")
async def generate(
    payload: GenerateIn,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _check_rate(f"{principal.user.id}:tts", 30)
    service = tts_service.TTSGenerationService(session)
    channel = None
    if payload.channel_id:
        from app.models import Channel

        channel = await session.get(Channel, payload.channel_id)
    try:
        config = await service.config_service.resolve(
            workspace_id=principal.workspace.id,
            channel=channel,
            explicit=tts_service.TTSOverride(
                provider=payload.provider,
                model=payload.model,
                voice_id=payload.voice_id,
                language=payload.language,
                output_format=payload.output_format,
                voice_settings=payload.voice_settings,
            ),
        )
        generated = await service.generate(workspace_id=principal.workspace.id,
                                           text=payload.text, config=config)
    except TTSError as exc:
        await _record_failure(session, principal, payload, exc)
        await session.commit()
        raise _tts_error(exc) from exc
    saved = await service.persist(
        generated=generated,
        workspace_id=principal.workspace.id,
        actor_id=principal.user.id,
        text=payload.text,
        config=config.as_dict(),
        request={k: v for k, v in payload.model_dump().items() if k != "text"},
        trigger="studio",
    )
    await session.commit()
    if not payload.preserve_text:
        saved.pop("text", None)
    saved["config"] = config.as_dict()
    return saved


async def _record_failure(session: AsyncSession, principal: Principal, payload: GenerateIn,
                          exc: TTSError) -> None:
    from app.models.tts_generation import TTSUsageLog

    generation = TTSGeneration(
        workspace_id=principal.workspace.id,
        provider=payload.provider or "unresolved",
        model=payload.model or "",
        voice_id=payload.voice_id,
        language=payload.language,
        input_text=payload.text,
        character_count=len(payload.text),
        status="failed",
        error_code=exc.code,
        error_message=exc.message,
        trigger="studio",
        is_test=True,
        request_key="tts-failure:" + hashlib.sha256(f"{time.time()}".encode()).hexdigest()[:32],
        created_by=principal.user.id,
        settings=payload.model_dump(exclude={"text"}),
    )
    session.add(generation)
    await session.flush()
    session.add(TTSUsageLog(
        workspace_id=principal.workspace.id, generation_id=generation.id,
        provider=generation.provider, model=generation.model, operation="tts_speech",
        usage_quantity=0, usage_unit="characters", estimated_cost=0, status="failed",
    ))


@router.post("/generate-dialogue")
async def generate_dialogue(
    payload: DialogueIn,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _check_rate(f"{principal.user.id}:tts-dialogue", 10)
    service = tts_service.TTSGenerationService(session)
    try:
        config = await service.config_service.resolve(
            workspace_id=principal.workspace.id,
            explicit=tts_service.TTSOverride(
                provider=payload.provider, model=payload.model, language=payload.language,
                output_format=payload.output_format, voice_settings=payload.voice_settings,
            ),
        )
        handle = await service.factory.build(principal.workspace.id, config.provider,
                                             model=config.model,
                                             output_format=config.output_format)
        lines = [DialogueLine(text=line.text, voice_id=line.voice_id) for line in payload.lines]
        from app.ports.tts import TTSConfig

        result = await handle.provider.generate_dialogue(
            lines,
            TTSConfig(text="\n".join(line.text for line in lines),
                      voice_id=",".join(sorted({line.voice_id for line in lines})),
                      model=config.model or "", language=config.language,
                      output_format=config.output_format,
                      voice_settings=config.voice_settings),
        )
    except TTSError as exc:
        raise _tts_error(exc) from exc
    generated = tts_service.GeneratedAudio(
        result=result, audio=result.audio, mime=result.mime, duration_s=result.duration_s,
        provider=handle.slug, model=result.model, voice_id=result.voice_id,
        output_format=result.output_format, estimated_cost_usd=result.estimated_cost_usd,
    )
    text = "\n".join(f"[{line.speaker or 'line'}] {line.text}" for line in payload.lines)
    saved = await service.persist(
        generated=generated, workspace_id=principal.workspace.id, actor_id=principal.user.id,
        text=text, config=config.as_dict(), trigger="studio",
    )
    saved["mode"] = "dialogue"
    await session.commit()
    return saved


@router.post("/compare")
async def compare(
    payload: CompareIn,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _check_rate(f"{principal.user.id}:tts-compare", 10)
    service = tts_service.TTSGenerationService(session)
    try:
        result = await tts_service.compare(
            service,
            workspace_id=principal.workspace.id,
            text=payload.text,
            language=payload.language,
            left=tts_service.ComparisonSide(
                provider=payload.left.provider, model=payload.left.model,
                voice_id=payload.left.voice_id, output_format=payload.left.output_format,
                voice_settings=payload.left.voice_settings,
            ),
            right=tts_service.ComparisonSide(
                provider=payload.right.provider, model=payload.right.model,
                voice_id=payload.right.voice_id, output_format=payload.right.output_format,
                voice_settings=payload.right.voice_settings,
            ),
        )
    finally:
        await session.commit()
    return result


# --------------------------------------------------------------------------- history / usage


@router.get("/generations")
async def generations(
    provider: str | None = None,
    status: str | None = None,
    trigger: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(TTSGeneration).where(TTSGeneration.workspace_id == principal.workspace.id)
    count_stmt = select(func.count(TTSGeneration.id)).where(
        TTSGeneration.workspace_id == principal.workspace.id
    )
    if provider:
        stmt = stmt.where(TTSGeneration.provider == provider)
        count_stmt = count_stmt.where(TTSGeneration.provider == provider)
    if status:
        stmt = stmt.where(TTSGeneration.status == status)
        count_stmt = count_stmt.where(TTSGeneration.status == status)
    if trigger:
        stmt = stmt.where(TTSGeneration.trigger == trigger)
        count_stmt = count_stmt.where(TTSGeneration.trigger == trigger)
    rows = list((await session.execute(
        stmt.order_by(desc(TTSGeneration.created_at)).limit(limit).offset(offset)
    )).scalars())
    total = await session.scalar(count_stmt)
    return {
        "items": [tts_service.generation_summary(r) | {"audio_url": _proxyable(r)} for r in rows],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
    }


def _proxyable(row: TTSGeneration) -> str | None:
    return f"/files/{row.audio_path}" if row.audio_path else None


@router.get("/generations/{generation_id}")
async def generation(
    generation_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await session.scalar(
        select(TTSGeneration).where(
            TTSGeneration.id == generation_id,
            TTSGeneration.workspace_id == principal.workspace.id,
        )
    )
    if row is None:
        raise NotFoundError("Generation not found")
    summary = tts_service.generation_summary(row)
    summary["chunk_manifest"] = row.chunk_manifest
    summary["settings"] = row.settings
    return summary


@router.get("/usage")
async def usage(
    days: int = Query(default=30, ge=1, le=180),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await tts_service.usage_summary(session, principal.workspace.id, days)


@router.get("/estimate")
async def estimate(
    text_length: int = Query(ge=0, le=MAX_TEXT),
    provider: str = "cartesia",
    model: str | None = None,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from app.services import pricing

    row = await session.scalar(
        select(AiProvider).where(
            AiProvider.workspace_id == principal.workspace.id,
            AiProvider.kind == "tts",
            AiProvider.slug == provider,
        )
    )
    est = pricing.estimate(provider=provider, model=model or "", characters=text_length,
                           models=list(row.models or []) if row else None)
    return asdict(est)


# --------------------------------------------------------------------------- settings


@router.get("/settings")
async def get_settings_(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = tts_service.TTSConfigurationService(session)
    row = await service.global_config(principal.workspace.id)
    resolved = None
    try:
        resolved = (await service.resolve(workspace_id=principal.workspace.id)).as_dict()
    except TTSError:
        resolved = None
    return {
        "workspace": _config_out(row) if row else None,
        "resolved": resolved,
        "precedence": list(tts_service.SCOPE_ORDER),
    }


def _config_out(row: TTSConfiguration) -> dict[str, Any]:
    return {
        "provider": row.provider_slug,
        "fallback_provider": row.fallback_provider_slug,
        "model": row.model,
        "voice_id": row.voice_id,
        "language": row.language,
        "output_format": row.output_format,
        "voice_settings": row.voice_settings,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.put("/settings")
async def update_settings_(
    payload: SettingsIn,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = tts_service.TTSConfigurationService(session)
    previous = await service.global_config(principal.workspace.id)
    before = _config_out(previous) if previous else None
    try:
        row = await service.set_global_config(
            principal.workspace.id,
            provider=payload.provider,
            actor_id=principal.user.id,
            fallback_provider=payload.fallback_provider or None,
            model=payload.model,
            voice_id=payload.voice_id,
            language=payload.language,
            output_format=payload.output_format,
            voice_settings=payload.voice_settings,
        )
    except ValidationAppError:
        raise
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="tts.settings.updated", target_type="tts_configuration",
                      target_id=str(row.id), request=request,
                      before=before, after=_config_out(row))
    await session.commit()
    return {"workspace": _config_out(row)}


# --------------------------------------------------------------------------- diagnostics


@router.post("/test")
async def test_generation(
    payload: TestIn,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Short synthesis used by the providers screen to prove a key works end-to-end."""
    _check_rate(f"{principal.user.id}:tts-test", 20)
    service = tts_service.TTSGenerationService(session)
    try:
        config = await service.config_service.resolve(
            workspace_id=principal.workspace.id,
            explicit=tts_service.TTSOverride(
                provider=payload.provider, model=payload.model, voice_id=payload.voice_id,
                output_format=payload.output_format, language=payload.language,
            ),
        )
        started = time.perf_counter()
        generated = await service.generate(workspace_id=principal.workspace.id, text=payload.text,
                                           config=config, allow_fallback=False)
        saved = await service.persist(
            generated=generated, workspace_id=principal.workspace.id,
            actor_id=principal.user.id, text=payload.text, config=config.as_dict(),
            trigger="studio",
        )
        await session.commit()
        return {
            "ok": True,
            "detail": f"{generated.provider} · {generated.model} · {generated.duration_s:.1f}s",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "audio_url": saved["audio_url"],
            "generation_id": saved["id"],
            "voice_id": generated.voice_id,
        }
    except TTSError as exc:
        await session.rollback()
        return {"ok": False, "detail": exc.message, "error_code": exc.code}


@router.get("/debug/resolved")
async def resolved_config(
    channel_id: uuid.UUID | None = None,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Shows exactly which level supplied each value — makes inheritance auditable."""
    from app.models import Channel

    channel = await session.get(Channel, channel_id) if channel_id else None
    service = tts_service.TTSConfigurationService(session)
    try:
        return (await service.resolve(workspace_id=principal.workspace.id,
                                      channel=channel)).as_dict()
    except TTSError as exc:
        raise _tts_error(exc) from exc


# --------------------------------------------------------------------------- channel voices


def _channel_override_out(setting) -> dict[str, Any] | None:  # type: ignore[no-untyped-def]
    if setting is None:
        return None
    config = dict(setting.voice_config or {})
    if not any([setting.voice_provider, setting.voice_model, setting.voice_id, config]):
        return None
    return {
        "provider": setting.voice_provider,
        "model": setting.voice_model,
        "voice_id": setting.voice_id,
        "language": config.get("language"),
        "output_format": config.get("output_format"),
        "fallback_provider": config.get("fallback_provider"),
        "fallback_on_transient": config.get("fallback_on_transient", True),
        "voice_settings": {k: v for k, v in config.items()
                           if k not in {"language", "output_format", "fallback_provider",
                                        "fallback_on_transient", "provider", "model", "voice_id"}},
    }


@router.get("/channels/{channel_id}")
async def get_channel_voice(
    channel_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from app.models import Channel, ChannelSetting

    channel = await session.get(Channel, channel_id)
    if channel is None or channel.workspace_id != principal.workspace.id:
        raise NotFoundError("Channel not found")
    setting = await session.scalar(
        select(ChannelSetting).where(ChannelSetting.channel_id == channel_id)
    )
    service = tts_service.TTSConfigurationService(session)
    resolved = None
    try:
        resolved = (await service.resolve(workspace_id=principal.workspace.id,
                                          channel=channel)).as_dict()
    except TTSError:
        pass
    return {"channel_id": str(channel_id), "override": _channel_override_out(setting),
            "resolved": resolved}


@router.put("/channels/{channel_id}")
async def set_channel_voice(
    channel_id: uuid.UUID,
    payload: ChannelVoiceIn,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from app.models import Channel, ChannelSetting

    channel = await session.get(Channel, channel_id)
    if channel is None or channel.workspace_id != principal.workspace.id:
        raise NotFoundError("Channel not found")
    if payload.provider and payload.provider not in tts_registry_slugs():
        raise ValidationAppError(f"Unknown TTS provider '{payload.provider}'")
    if payload.fallback_provider and payload.fallback_provider == payload.provider:
        raise ValidationAppError("The fallback provider must differ from the primary provider")
    setting = await session.scalar(
        select(ChannelSetting).where(ChannelSetting.channel_id == channel_id)
    )
    if setting is None:
        setting = ChannelSetting(channel_id=channel_id)
        session.add(setting)
    before = _channel_override_out(setting)
    if payload.clear:
        setting.voice_provider = None
        setting.voice_id = None
        setting.voice_model = None
        setting.voice_config = {}
    else:
        if payload.provider is not None:
            setting.voice_provider = payload.provider or None
        if payload.voice_id is not None:
            setting.voice_id = payload.voice_id or None
        if payload.model is not None:
            setting.voice_model = payload.model or None
        config = dict(setting.voice_config or {})
        for key, value in {
            "language": payload.language,
            "output_format": payload.output_format,
            "fallback_provider": payload.fallback_provider,
        }.items():
            if value is not None:
                config[key] = value or None
        config.update({k: v for k, v in (payload.voice_settings or {}).items() if v is not None})
        setting.voice_config = {k: v for k, v in config.items() if v is not None}
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="channel.voice.updated", target_type="channel_setting",
                      target_id=str(channel_id), request=request, before=before,
                      after=_channel_override_out(setting))
    await session.commit()
    resolved = None
    try:
        resolved = (await tts_service.TTSConfigurationService(session).resolve(
            workspace_id=principal.workspace.id, channel=channel)).as_dict()
    except TTSError:
        pass
    return {"channel_id": str(channel_id), "override": _channel_override_out(setting),
            "resolved": resolved}


def tts_registry_slugs() -> set[str]:
    from app.adapters.tts_registry import ADAPTERS

    return set(ADAPTERS)


def _unused(*_: Any) -> None:  # pragma: no cover
    del _


__all__ = ["router", "SelectionIn", "VoiceSettings"]
