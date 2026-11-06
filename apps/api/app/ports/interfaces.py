"""Ports (interfaces) for every external system.

Adapters live in ``factory_ai.adapters`` (LLM/TTS/Image), ``factory_media`` (renderer/storage)
and ``factory_ai.youtube``. Services depend only on these Protocols, never on a vendor SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class ProviderError(RuntimeError):
    """Raised by adapters when a provider call fails (after its own retries)."""

    def __init__(self, message: str, *, status: int | None = None, retry_after_s: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after_s = retry_after_s


class RateLimitedError(ProviderError):
    """Provider signalled 429 / quota exhaustion."""


# --------------------------------------------------------------------------- usage


@dataclass(slots=True)
class Usage:
    """Cost & accounting for one provider call."""

    provider: str = ""
    model: str = ""
    operation: str = "llm_chat"
    input_tokens: int = 0
    output_tokens: int = 0
    units: float = 1.0
    unit_label: str = "request"
    cost_usd: float = 0.0
    latency_ms: int = 0


# --------------------------------------------------------------------------- llm


@dataclass(slots=True)
class Message:
    role: str  # system | user | assistant
    content: str


@dataclass(slots=True)
class LLMResult:
    content: str
    usage: Usage
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_schema: dict[str, Any] | None = None,
        timeout_s: float = 120.0,
    ) -> LLMResult: ...

    async def health(self) -> tuple[bool, str]: ...


# --------------------------------------------------------------------------- tts


@dataclass(slots=True)
class SynthesizedAudio:
    audio: bytes
    mime: str
    duration_s: float
    usage: Usage
    sample_rate: int = 44100


@runtime_checkable
class TTSProvider(Protocol):
    name: str

    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str,
        model: str | None = None,
        speed: float = 1.0,
        emotion: str | None = None,
        language: str = "en",
        timeout_s: float = 90.0,
    ) -> SynthesizedAudio: ...

    async def voices(self) -> list[dict[str, Any]]: ...

    async def health(self) -> tuple[bool, str]: ...


# --------------------------------------------------------------------------- image


@dataclass(slots=True)
class GeneratedImage:
    data: bytes
    mime: str
    width: int
    height: int
    usage: Usage


@runtime_checkable
class ImageProvider(Protocol):
    name: str

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str | None = None,
        aspect_ratio: str = "16:9",
        model: str | None = None,
        reference_image: bytes | None = None,
        seed: int | None = None,
        timeout_s: float = 180.0,
    ) -> GeneratedImage: ...

    async def health(self) -> tuple[bool, str]: ...


# --------------------------------------------------------------------------- storage


@dataclass(slots=True)
class StoredObject:
    key: str
    url: str
    bytes: int
    checksum_sha256: str


@runtime_checkable
class Storage(Protocol):
    backend: str

    async def put_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> StoredObject: ...

    async def get_bytes(self, key: str) -> bytes: ...

    def url_for(self, key: str) -> str: ...

    async def delete(self, key: str) -> None: ...

    async def health(self) -> tuple[bool, str]: ...


# --------------------------------------------------------------------------- video renderer


@dataclass(slots=True)
class SceneClip:
    scene_id: str
    index: int
    image_key: str
    audio_key: str | None
    duration_s: float
    caption: str
    transition: str = "fade"
    ken_burns: bool = True


@dataclass(slots=True)
class RenderSpec:
    render_id: str
    project_id: str
    title: str
    clips: list[SceneClip]
    width: int = 1920
    height: int = 1080
    fps: int = 30
    template: str = "youtube-editorial"
    music_key: str | None = None
    brand: str = "FACTORY"


@dataclass(slots=True)
class StoryboardRenderSpec:
    """What the Remotion engine needs: the resolved storyboard plus asset locations.

    ``spec`` is the JSON passed to the composition (see
    ``services/media-engine/remotion/src/types.ts``); asset sources are local paths staged by the
    renderer into a temporary public directory. ``scene_keys`` maps scene id → storage key so a
    scene-only re-render can stage just the scenes it needs.
    """

    render_id: str
    project_id: str
    composition_id: str
    spec: dict[str, Any]
    assets: list[dict[str, str]] = field(default_factory=list)
    stills: list[dict[str, Any]] = field(default_factory=list)
    stills_only: bool = False
    cancel_token: str | None = None
    concurrency: int | None = None


@dataclass(slots=True)
class RenderProgress:
    stage: str  # bundling | rendering | encoding | muxing
    progress: float  # 0..1
    rendered_frames: int = 0
    total_frames: int = 0
    ffmpeg_progress: float | None = None


@dataclass(slots=True)
class RenderArtifact:
    output_path: str
    bytes: int
    elapsed_s: float


@dataclass(slots=True)
class RenderOutput:
    video_key: str
    subtitle_key: str | None
    duration_s: float
    bytes: int
    width: int
    height: int


@runtime_checkable
class VideoRenderer(Protocol):
    """Video composition/rendering port. The only implementation is Remotion."""

    async def render(
        self,
        spec: StoryboardRenderSpec,
        *,
        on_progress: Any = None,
    ) -> tuple[RenderArtifact, dict[str, Any]]: ...

    async def validate(
        self, path: Any, *, expected: dict[str, Any] | None = None
    ) -> tuple[bool, list[dict[str, Any]], list[str], dict[str, Any]]: ...

    async def health(self) -> tuple[bool, str]: ...


# --------------------------------------------------------------------------- youtube


@dataclass(slots=True)
class UploadRequest:
    title: str
    description: str
    tags: list[str]
    privacy: str
    made_for_kids: bool
    scheduled_for: datetime | None
    video_path: str | None = None
    video_bytes: bytes | None = None
    thumbnail_bytes: bytes | None = None
    mime_type: str = "video/mp4"


@dataclass(slots=True)
class UploadResult:
    youtube_video_id: str
    url: str


@dataclass(slots=True)
class VideoStats:
    youtube_video_id: str
    views: int
    impressions: int | None
    ctr: float | None
    watch_time_minutes: float
    avg_view_duration_s: float | None
    subscribers_gained: int
    likes: int
    comments: int


@runtime_checkable
class YouTubeService(Protocol):
    async def upload(self, access_token: str, request: UploadRequest) -> UploadResult: ...

    async def fetch_stats(self, access_token: str, video_ids: list[str]) -> list[VideoStats]: ...

    async def channel_info(self, access_token: str) -> dict[str, Any]: ...
