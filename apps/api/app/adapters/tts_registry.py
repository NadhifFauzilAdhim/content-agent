"""TTS adapter registry: builds a :class:`~app.ports.tts_provider.TTSProvider` by slug.

This module is the only place vendor classes are imported. Provider *configuration* (key, model,
voice, output format) arrives already resolved from :class:`app.services.tts.TTSProviderFactory`,
so adapters stay stateless with respect to the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.tts_cartesia import CartesiaProvider
from app.adapters.tts_elevenlabs import ElevenLabsProvider
from app.adapters.tts_mock import MockTTSProvider
from app.ports.tts import TTSConfigError
from app.ports.tts_provider import TTSProvider

ADAPTERS: dict[str, type] = {
    "cartesia": CartesiaProvider,
    "elevenlabs": ElevenLabsProvider,
    "mock": MockTTSProvider,
}

#: Descriptive defaults used by the providers screen and the seed script.
CATALOG: dict[str, dict[str, Any]] = {
    "cartesia": {
        "label": "Cartesia",
        "vendor": "Cartesia",
        "docs": "https://docs.cartesia.ai/api-reference/tts/bytes",
        "key_hint": "sk_car_…",
        "default_model": "sonic-3.6",
        "default_voice": "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",  # Skylar (documented example)
        "default_format": "wav/44100/pcm_s16le",
    },
    "elevenlabs": {
        "label": "ElevenLabs",
        "vendor": "ElevenLabs",
        "docs": "https://elevenlabs.io/docs/api-reference/text-to-speech/convert",
        "key_hint": "xi-…",
        "default_model": "eleven_multilingual_v2",
        "default_voice": "21m00Tcm4TlvDq8ikWAM",  # Rachel (official default voice)
        "default_format": "mp3_44100_128",
    },
    "mock": {
        "label": "Mock TTS",
        "vendor": "Factory",
        "docs": None,
        "key_hint": None,
        "default_model": "mock-tts",
        "default_voice": "mock-narrator",
        "default_format": "wav/22050/pcm_s16le",
    },
}


@dataclass(slots=True)
class AdapterSettings:
    slug: str
    api_key: str | None
    base_url: str | None = None
    model: str | None = None
    voice_id: str | None = None
    output_format: str | None = None


def build(slug: str, *, api_key: str | None, base_url: str | None = None, model: str | None = None,
          voice_id: str | None = None, output_format: str | None = None) -> TTSProvider:
    if slug == "cartesia":
        if not api_key:
            raise TTSConfigError("Cartesia has no API key configured")
        return CartesiaProvider(api_key, base_url=base_url, model=model, voice_id=voice_id,
                                output_format=output_format)
    if slug == "elevenlabs":
        if not api_key:
            raise TTSConfigError("ElevenLabs has no API key configured")
        return ElevenLabsProvider(api_key, base_url=base_url, model=model, voice_id=voice_id,
                                  output_format=output_format)
    if slug == "mock":
        return MockTTSProvider(model=model, voice_id=voice_id, output_format=output_format)
    raise TTSConfigError(f"Unknown TTS provider '{slug}'")


def supported() -> list[str]:
    return sorted(ADAPTERS)


__all__ = ["ADAPTERS", "CATALOG", "AdapterSettings", "build", "supported"]
