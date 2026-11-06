"""Mock TTS for development.

Generates a quiet tone bed whose length matches an estimated speaking rate, so the video
pipeline (timing, subtitles, mixing, chunking) can be exercised without spending credits.
Every result is labelled ``mock`` in storage and in the UI. It is never selected when a real
provider has a credential.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from typing import Any

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


def _tone(text: str, *, speed: float = 1.0, rate: int = 22050) -> tuple[bytes, float]:
    words = max(1, len(text.split()))
    seconds = max(0.8, min(60.0, words / (2.6 * max(speed, 0.1))))
    buffer = io.BytesIO()
    frames = int(rate * seconds)
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        chunk = bytearray()
        for i in range(frames):
            sample = int(380 * math.sin(2 * math.pi * 220 * i / rate))  # -34 dBFS marker
            chunk += struct.pack("<h", sample)
        wav.writeframes(bytes(chunk))
    return buffer.getvalue(), round(seconds, 2)


class MockTTSProvider:
    name = "mock"
    label = "Mock TTS"
    is_mock = True

    def __init__(
        self,
        *,
        model: str | None = None,
        voice_id: str | None = None,
        output_format: str | None = None,
        **_kwargs: Any,
    ) -> None:
        self.default_model = model or "mock-tts"
        self.default_voice = voice_id or "mock-narrator"
        self.default_format = output_format or "wav/22050/pcm_s16le"

    async def test_connection(self) -> TestResult:
        return TestResult(True, "Mock TTS · duration-only audio, no provider calls", 2,
                          [{"name": "local", "ok": True, "detail": "mock adapter"}])

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("mock-tts", "Mock TTS", "Duration-only tone at an estimated speaking rate.",
                          max_chars=None, supports_dialogue=True)]

    async def list_voices(self, *, language: str | None = None, query: str | None = None) -> list[VoiceInfo]:
        voices = [
            VoiceInfo("mock-narrator", "Mock narrator", language="en", gender="neutral", category="mock"),
            VoiceInfo("mock-child", "Mock child", language="en", gender="neutral", category="mock"),
            VoiceInfo("mock-guest", "Mock guest", language="en", gender="neutral", category="mock"),
        ]
        if query:
            voices = [v for v in voices if query.lower() in v.name.lower() or query == v.voice_id]
        return voices

    def output_formats(self, model: str) -> list[OutputFormat]:
        return [
            OutputFormat("wav/22050/pcm_s16le", "WAV · 22.05 kHz", "wav", "audio/wav", 22050),
            OutputFormat("mp3/22050/64000", "MP3 · 22.05 kHz (re-encoded)", "mp3", "audio/mpeg", 22050, 64000),
        ]

    def voice_params(self, model: str) -> list[ParamSpec]:
        return [ParamSpec("speed", "Speed", "number", 0.5, 2.0, 1.0, help="Changes the estimated duration.")]

    def language_supported(self, model: str, language: str) -> bool:
        return True

    async def generate_speech(self, config: TTSConfig) -> SynthesisResult:
        speed = float((config.voice_settings or {}).get("speed", config.speed or 1.0))
        data, seconds = _tone(config.text, speed=speed)
        return SynthesisResult(
            audio=data,
            mime="audio/wav",
            duration_s=seconds,
            provider=self.name,
            model=config.model or "mock-tts",
            voice_id=config.voice_id or "mock-narrator",
            output_format="wav/22050/pcm_s16le",
            sample_rate=22050,
            character_count=len(config.text),
            latency_ms=3,
            estimated_cost_usd=0.0,
            warnings=["Mock TTS: tone only, not speech."],
        )

    async def generate_dialogue(self, lines: list[DialogueLine], config: TTSConfig) -> SynthesisResult:
        config = TTSConfig(
            text=" ".join(line.text for line in lines),
            voice_id=lines[0].voice_id if lines else "mock-narrator",
            model=config.model,
            language=config.language,
            output_format=config.output_format,
            voice_settings=config.voice_settings,
        )
        return await self.generate_speech(config)

    # -- port compatibility ------------------------------------------------
    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str = "mock-narrator",
        model: str | None = None,
        speed: float = 1.0,
        emotion: str | None = None,
        language: str = "en",
        timeout_s: float = 5.0,
    ):  # noqa: ANN201 - returns app.ports.interfaces.SynthesizedAudio
        """Legacy ``TTSProvider.synthesize`` used by the voice agent's per-chunk path."""
        from app.ports.interfaces import SynthesizedAudio, Usage

        result = await self.generate_speech(
            TTSConfig(text=text, voice_id=voice_id, model=model or self.default_model,
                      language=language, voice_settings={"speed": speed, "emotion": emotion})
        )
        return SynthesizedAudio(
            audio=result.audio,
            mime=result.mime,
            duration_s=result.duration_s,
            sample_rate=result.sample_rate,
            usage=Usage(provider=self.name, model=result.model, operation="tts",
                        units=len(text), unit_label="chars", latency_ms=result.latency_ms),
        )

    async def voices(self) -> list[dict]:
        return [
            {"voice_id": v.voice_id, "name": v.name, "language": v.language}
            for v in await self.list_voices()
        ]

    async def health(self) -> tuple[bool, str]:
        result = await self.test_connection()
        return result.ok, result.detail
