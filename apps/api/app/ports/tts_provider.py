"""Unified TTS provider interface.

Everything that generates narration talks to ``TTSProvider`` — the voice agent, Audio Studio,
A/B comparison and connection tests. ``app.adapters.tts_registry`` holds the vendor
implementations and the factory; nothing above the adapter layer branches on a provider name.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.ports.tts import (
    DialogueLine,
    ModelInfo,
    OutputFormat,
    ParamSpec,
    SynthesisResult,
    TestResult,
    TTSConfig,
    VoiceInfo,
)


class TTSProvider(Protocol):
    name: str  # stable slug, e.g. "cartesia"
    label: str  # human name, e.g. "Cartesia"
    is_mock: bool

    # -- introspection -----------------------------------------------------
    async def test_connection(self) -> TestResult: ...

    async def list_models(self) -> list[ModelInfo]: ...

    async def list_voices(self, *, language: str | None = None, query: str | None = None) -> list[VoiceInfo]: ...

    def output_formats(self, model: str) -> list[OutputFormat]: ...

    def voice_params(self, model: str) -> list[ParamSpec]: ...

    def language_supported(self, model: str, language: str) -> bool: ...

    # -- generation --------------------------------------------------------
    async def generate_speech(self, config: TTSConfig) -> SynthesisResult: ...

    async def generate_dialogue(self, lines: list[DialogueLine], config: TTSConfig) -> SynthesisResult: ...

    # -- convenience for the UI -------------------------------------------
    async def voice_preview(self, voice: VoiceInfo) -> bytes | None:
        """Raw preview bytes if the provider publishes one; adapters may fetch it with auth."""
        return None


@runtime_checkable
class CancellableTTSProvider(Protocol):
    """Adapters that can abort an in-flight HTTP request (used by Audio Studio cancel)."""

    def cancel(self, token: str) -> bool: ...


def describe(provider: TTSProvider) -> dict[str, Any]:
    return {"slug": provider.name, "label": provider.label, "mock": provider.is_mock}
