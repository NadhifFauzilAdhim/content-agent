"""Voice, Visual and Video Production agents — these orchestrate provider ports."""

from __future__ import annotations

import asyncio
import hashlib

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, AgentError, AgentResult
from app.agents.contracts import Contract
from app.agents.generation import usage_zero
from app.ports.interfaces import (
    StoredObject,
    Usage,
)
from app.ports.tts import Chunk, TTSError, TTSInvalidRequestError
from app.services.chunking import split_text

# --------------------------------------------------------------------------- voice


class VoiceSceneRequest(Contract):
    scene_id: str
    index: int
    text: str
    voice_id: str | None = None
    emotion: str | None = None
    speed: float | None = None
    voice_settings: dict = Field(default_factory=dict)


class VoiceRequest(Contract):
    language: str = "en"
    speed: float = 1.0
    scenes: list[VoiceSceneRequest] = Field(min_length=1)
    # Per-workflow override of the TTS configuration (provider/model/voice/output_format).
    voice: dict | None = None


class VoiceSceneResult(BaseModel):
    scene_id: str
    index: int
    key: str
    duration_s: float
    provider: str
    voice_id: str
    bytes: int
    mime: str
    model: str = ""
    output_format: str = ""
    voice_settings: dict = Field(default_factory=dict)
    chunk_count: int = 1
    estimated_cost_usd: float = 0.0
    fallback_used: bool = False


class VoiceResult(BaseModel):
    scenes: list[VoiceSceneResult]
    total_duration_s: float
    provider: str = ""
    model: str = ""
    estimated_cost_usd: float = 0.0


class VoiceGenerationAgent:
    key = "voice_generation"
    name = "Voice Generation"
    InputModel = VoiceRequest
    OutputModel = VoiceResult

    async def run(self, ctx: AgentContext, payload: VoiceRequest) -> AgentResult[VoiceResult]:
        tts = ctx.require_tts()
        storage = ctx.require_storage()
        default_voice = ctx.params.get("default_voice_id") or ""
        raw_config = dict(ctx.params.get("tts_config") or {})
        chunk_limit = int(ctx.params.get("max_chunk_chars") or 0) or None
        semaphore = asyncio.Semaphore(int(ctx.params.get("concurrency", 3)))
        provider_name = getattr(tts, "name", "unknown")
        model_name = raw_config.get("model") or ""
        warnings: list[str] = []

        async def synthesize_scene(scene: VoiceSceneRequest):
            """Chunk long narration, preserving order and retrying only the failed chunk."""
            text = scene.text.strip()
            chunks = split_text(text, chunk_limit) if chunk_limit else [Chunk(0, scene.text)]

            parts: list[bytes] = []
            durations: list[float] = []
            for chunk in chunks:
                audio = await _retryable(
                    lambda c=chunk: tts.synthesize(
                        text=c.text,
                        voice_id=scene.voice_id or default_voice,
                        model=model_name or None,
                        speed=float(scene.speed or raw_config.get("speed") or payload.speed or 1.0),
                        emotion=scene.emotion,
                        language=payload.language,
                    ),
                    retries=int(ctx.params.get("tts_retries", 2)),
                )
                parts.append(audio.audio)
                durations.append(audio.duration_s)
            if len(parts) == 1:
                return parts[0], durations[0], len(chunks)
            from app.adapters import audio as audio_tools

            if any(p[:4] != b"RIFF" for p in parts):
                parts = [audio_tools.resample_to_wav(p) for p in parts]
            combined = await audio_tools.combine(parts, mime="audio/wav", output_format="wav")
            audio_tools.validate_wav(combined, provider=provider_name)
            return combined, audio_tools.duration_of(combined), len(chunks)

        async def one(scene: VoiceSceneRequest) -> tuple[VoiceSceneResult, Usage]:
            async with semaphore:
                audio_bytes, duration, chunk_count = await synthesize_scene(scene)
            ext = "wav" if audio_bytes[:4] == b"RIFF" else "mp3"
            mime = "audio/wav" if ext == "wav" else "audio/mpeg"
            key = f"p/{ctx.project_id}/audio/scene-{scene.index:02d}-{_hash(scene.text)}.{ext}"
            stored: StoredObject = await storage.put_bytes(key, audio_bytes, mime)
            return (
                VoiceSceneResult(
                    scene_id=scene.scene_id,
                    index=scene.index,
                    key=stored.key,
                    duration_s=duration,
                    provider=provider_name,
                    voice_id=scene.voice_id or default_voice,
                    bytes=stored.bytes,
                    mime=mime,
                    model=model_name,
                    output_format=str(raw_config.get("output_format") or ""),
                    voice_settings=dict(raw_config.get("voice_settings") or {}),
                    chunk_count=chunk_count,
                ),
                Usage(
                    provider=provider_name,
                    model=model_name or "tts",
                    operation="tts",
                    units=len(scene.text),
                    unit_label="chars",
                    latency_ms=0,
                ),
            )

        try:
            results = await asyncio.gather(*(one(s) for s in payload.scenes))
        except TTSInvalidRequestError as exc:
            raise AgentError(str(exc), agent_key=self.key, retryable=False) from exc
        except TTSError as exc:
            raise AgentError(str(exc), agent_key=self.key, retryable=exc.transient) from exc
        total = sum(r.duration_s for r, _ in results)
        usage = _combine([u for _, u in results], "tts")
        if provider_name == "mock":
            warnings.append("Audio generated by mock TTS (duration-only tone).")
        return AgentResult(
            output=VoiceResult(
                scenes=[r for r, _ in results],
                total_duration_s=round(total, 2),
                provider=provider_name,
                model=model_name,
                estimated_cost_usd=round(sum(r.estimated_cost_usd for r, _ in results), 6),
            ),
            usage=usage,
            provider=provider_name,
            model=model_name or "tts",
            artifacts={f"scene:{r.index}:audio": r.key for r, _ in results},
            warnings=warnings,
        )


async def _retryable(call, *, retries: int = 2):  # type: ignore[no-untyped-def]
    """Retry one chunk on transient failures; configuration errors propagate immediately."""
    last: TTSError | None = None
    for attempt in range(retries + 1):
        try:
            return await call()
        except TTSError as exc:
            last = exc
            if not exc.transient or attempt >= retries:
                raise
            await asyncio.sleep(min(2 ** attempt, 8))
    if last is not None:
        raise last



# --------------------------------------------------------------------------- visual


class VisualSceneRequest(Contract):
    scene_id: str
    index: int
    prompt: str
    negative_prompt: str | None = None
    image_prompt_ref: str | None = None


class VisualRequest(Contract):
    aspect_ratio: str = "16:9"
    style_suffix: str = ""
    scenes: list[VisualSceneRequest] = Field(min_length=1)
    reference_scene_index: int | None = None


class VisualSceneResult(BaseModel):
    scene_id: str
    index: int
    key: str
    url: str
    width: int
    height: int
    provider: str
    model: str
    bytes: int
    checksum: str


class VisualResult(BaseModel):
    scenes: list[VisualSceneResult]


class VisualGenerationAgent:
    key = "visual_generation"
    name = "Visual Generation"
    InputModel = VisualRequest
    OutputModel = VisualResult

    async def run(self, ctx: AgentContext, payload: VisualRequest) -> AgentResult[VisualResult]:
        image = ctx.require_image()
        storage = ctx.require_storage()
        concurrency = int(ctx.params.get("concurrency", 3))
        semaphore = asyncio.Semaphore(concurrency)
        retries = int(ctx.params.get("max_attempts", 3))
        warnings: list[str] = []

        async def generate(scene: VisualSceneRequest) -> tuple[VisualSceneResult, Usage]:
            prompt = scene.prompt + (f" {payload.style_suffix}" if payload.style_suffix else "")
            last_error: Exception | None = None
            for attempt in range(1, retries + 1):
                try:
                    async with semaphore:
                        img = await image.generate(
                            prompt=prompt,
                            negative_prompt=scene.negative_prompt,
                            aspect_ratio=payload.aspect_ratio,
                            model=ctx.model or None,
                            seed=None if attempt == 1 else attempt,
                        )
                    ext = "png" if "png" in img.mime else "jpg"
                    key = f"p/{ctx.project_id}/images/scene-{scene.index:02d}-{_hash(prompt)[:10]}.{ext}"
                    stored = await storage.put_bytes(key, img.data, img.mime)
                    return (
                        VisualSceneResult(
                            scene_id=scene.scene_id,
                            index=scene.index,
                            key=stored.key,
                            url=stored.url,
                            width=img.width,
                            height=img.height,
                            provider=img.usage.provider,
                            model=img.usage.model,
                            bytes=stored.bytes,
                            checksum=stored.checksum_sha256,
                        ),
                        img.usage,
                    )
                except Exception as exc:  # noqa: BLE001 - retried then surfaced
                    last_error = exc
                    if attempt < retries:
                        await asyncio.sleep(min(30, 2 ** attempt))
            raise AgentError(
                f"Visual generation failed for scene {scene.index}: {last_error}",
                agent_key=self.key,
            )

        results = await asyncio.gather(*(generate(s) for s in payload.scenes))
        usage = _combine([u for _, u in results], "image")
        if usage.provider == "mock":
            warnings.append("Images are Pillow mock cards — configure an image provider.")
        return AgentResult(
            output=VisualResult(scenes=[r for r, _ in results]),
            usage=usage,
            provider=usage.provider,
            model="image",
            artifacts={f"scene:{r.index}:image": r.key for r, _ in results},
            warnings=warnings,
        )


# --------------------------------------------------------------------------- video
#
# Composition and encoding are owned by the Remotion engine (app/services/render.py and
# services/media-engine/remotion). This agent only validates that a render job is well-formed
# before it is queued, so the pipeline fails fast on missing assets instead of inside the renderer.


class RenderSceneInput(Contract):
    scene_id: str
    index: int
    image_key: str | None = None
    audio_key: str | None = None
    duration_s: float
    caption: str
    transition: str = "fade"


class RenderRequest(Contract):
    render_id: str
    title: str
    width: int = 1920
    height: int = 1080
    fps: int = 30
    template: str = "youtube-editorial"
    scenes: list[RenderSceneInput]


class RenderResult(BaseModel):
    template: str
    width: int
    height: int
    fps: int
    scene_count: int
    duration_s: float
    ready: bool = True


class VideoProductionAgent:
    key = "video_production"
    name = "Video Production"
    InputModel = RenderRequest
    OutputModel = RenderResult

    async def run(self, ctx: AgentContext, payload: RenderRequest) -> AgentResult[RenderResult]:
        if not payload.scenes:
            raise AgentError("A render needs at least one scene", agent_key=self.key, retryable=False)
        missing = [s.index for s in payload.scenes if not s.image_key]
        if missing:
            raise AgentError(
                f"Scenes {missing} have no image asset; run the visual stage first",
                agent_key=self.key,
                retryable=False,
            )
        duration = sum(float(s.duration_s or 0) for s in payload.scenes)
        return AgentResult(
            output=RenderResult(
                template=payload.template,
                width=payload.width,
                height=payload.height,
                fps=payload.fps,
                scene_count=len(payload.scenes),
                duration_s=round(duration, 2),
            ),
            usage=Usage(provider="remotion", model=payload.template, operation="validate",
                        units=len(payload.scenes), unit_label="scene"),
            provider="remotion",
            model=payload.template,
            artifacts={f"scene:{s.index}:image": s.image_key or "" for s in payload.scenes},
        )


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _combine(usages: list[Usage], operation: str) -> Usage:
    providers = {u.provider for u in usages}
    return Usage(
        provider=",".join(sorted(providers)) if providers else "n/a",
        model=operation,
        operation=operation,
        input_tokens=sum(u.input_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
        units=sum(u.units for u in usages),
        unit_label=usages[0].unit_label if usages else "request",
        cost_usd=sum(u.cost_usd for u in usages),
        latency_ms=max((u.latency_ms for u in usages), default=0),
    )


__all__ = [
    "RenderRequest",
    "RenderResult",
    "RenderSceneInput",
    "VideoProductionAgent",
    "VisualGenerationAgent",
    "VisualRequest",
    "VisualSceneRequest",
    "VoiceGenerationAgent",
    "VoiceRequest",
    "VoiceSceneRequest",
    "usage_zero",
]
