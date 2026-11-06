"""Provider-neutral text-to-speech domain types.

Adapters translate these to vendor payloads; services and the voice agent never see a
provider-specific field name. Capabilities are always reported by the provider (or, when the
provider does not expose capabilities, by a documented per-model table in the adapter) so the UI
can hide controls that the selected model does not support instead of failing at generation time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class TTSError(Exception):
    """Base class for TTS failures with a stable machine-readable code."""

    code = "tts_error"
    #: Whether a fallback provider may legitimately be tried.
    transient = False

    def __init__(self, message: str, *, detail: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class TTSTransientError(TTSError):
    """Timeout, 5xx, network failure or rate limit that survived retries."""

    code = "provider_unavailable"
    transient = True


class TTSRateLimitedError(TTSTransientError):
    code = "rate_limited"

    def __init__(self, message: str, *, retry_after_s: float | None = None, detail: Any = None) -> None:
        super().__init__(message, detail=detail)
        self.retry_after_s = retry_after_s


class TTSAuthError(TTSError):
    code = "invalid_credentials"
    transient = False


class TTSInvalidRequestError(TTSError):
    """Bad voice id, unsupported parameter, text too long, … — never auto-fallback."""

    code = "invalid_request"
    transient = False


class TTSContentError(TTSError):
    """Audio came back empty, truncated or unreadable."""

    code = "invalid_audio"
    transient = False


class TTSConfigError(TTSError):
    """Provider/model/voice not configured, unknown, or disabled."""

    code = "not_configured"
    transient = False


# --------------------------------------------------------------------------- descriptors


@dataclass(slots=True)
class ParamSpec:
    key: str
    label: str
    kind: str = "number"  # number | enum | boolean
    minimum: float | None = None
    maximum: float | None = None
    default: Any = None
    options: list[dict[str, Any]] = field(default_factory=list)  # [{value, label}]
    help: str | None = None


@dataclass(slots=True)
class OutputFormat:
    id: str  # provider-native identifier, e.g. mp3_44100_128 or wav/44100/pcm_s16le
    label: str
    container: str  # wav | mp3 | pcm
    mime: str
    sample_rate: int
    bit_rate: int | None = None
    encoding: str | None = None


@dataclass(slots=True)
class VoiceInfo:
    voice_id: str
    name: str
    language: str | None = None
    locale: str | None = None
    gender: str | None = None
    category: str | None = None
    description: str | None = None
    preview_url: str | None = None  # private URLs are re-served through the API
    labels: dict[str, str] = field(default_factory=dict)
    own_voice: bool = False


@dataclass(slots=True)
class ModelInfo:
    id: str
    name: str
    description: str | None = None
    max_chars: int | None = None
    languages: list[str] = field(default_factory=list)
    supports_dialogue: bool = False
    stereo: bool = False
    deprecated: bool = False


@dataclass(slots=True)
class TTSConfig:
    """A fully-resolved generation request (after configuration inheritance)."""

    text: str
    voice_id: str
    model: str
    language: str = "en"
    output_format: str | None = None
    voice_settings: dict[str, Any] = field(default_factory=dict)
    seed: int | None = None
    speed: float | None = None
    emotion: str | None = None
    prior_text: str | None = None
    next_text: str | None = None


@dataclass(slots=True)
class DialogueLine:
    text: str
    voice_id: str


@dataclass(slots=True)
class SynthesisResult:
    audio: bytes
    mime: str
    duration_s: float
    provider: str
    model: str
    voice_id: str
    output_format: str
    sample_rate: int
    character_count: int
    latency_ms: int
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float | None = None
    request_id: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TestResult:
    ok: bool
    detail: str
    latency_ms: int = 0
    checks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class Chunk:
    index: int
    text: str
