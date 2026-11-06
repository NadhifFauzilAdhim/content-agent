"""ElevenLabs adapter — ``POST /v1/text-to-speech/{voice_id}`` and ``POST /v1/text-to-dialogue``.

Behaviour follows the current API reference:

* Auth header ``xi-api-key``.
* ``GET /v1/models`` is the source of truth for models *and* their capabilities
  (``can_do_text_to_speech``, ``can_use_style``, ``can_use_speaker_boost``,
  ``maximum_text_length_per_request``, ``languages``, ``model_rates.character_cost_multiplier``).
  The UI only enables voice settings a model actually supports.
* ``GET /v2/voices`` (paginated, filterable) lists the workspace, library and premade voices;
  ``preview_url`` files are public and proxied through the API for playback.
* ``language_code`` is ignored (and rejected for some models) when unsupported, so it is only
  sent when the model advertises the language. ``eleven_multilingual_v2`` does not accept it.
* Multi-speaker narration uses ``/v1/text-to-dialogue`` with up to 10 unique voices and ~2,000
  characters per request.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.adapters import audio as audio_tools
from app.adapters.tts_http import _json, request_with_retry
from app.core.logging import get_logger
from app.ports.tts import (
    DialogueLine,
    ModelInfo,
    OutputFormat,
    ParamSpec,
    SynthesisResult,
    TestResult,
    TTSConfig,
    TTSError,
    TTSInvalidRequestError,
    VoiceInfo,
)

log = get_logger("factory.tts.elevenlabs")

API_BASE = "https://api.elevenlabs.io"

# Output formats offered by the current API reference. 44.1 kHz PCM/WAV and 192 kbps MP3 need the
# Pro / Creator tiers respectively — surfaced as a hint, not enforced client-side.
OUTPUT_FORMATS: list[OutputFormat] = [
    OutputFormat("mp3_44100_128", "MP3 · 44.1 kHz · 128 kbps", "mp3", "audio/mpeg", 44100, 128000),
    OutputFormat("mp3_44100_192", "MP3 · 44.1 kHz · 192 kbps (Creator+)", "mp3", "audio/mpeg", 44100, 192000),
    OutputFormat("mp3_44100_96", "MP3 · 44.1 kHz · 96 kbps", "mp3", "audio/mpeg", 44100, 96000),
    OutputFormat("mp3_44100_64", "MP3 · 44.1 kHz · 64 kbps", "mp3", "audio/mpeg", 44100, 64000),
    OutputFormat("mp3_44100_32", "MP3 · 44.1 kHz · 32 kbps", "mp3", "audio/mpeg", 44100, 32000),
    OutputFormat("mp3_22050_32", "MP3 · 22.05 kHz · 32 kbps", "mp3", "audio/mpeg", 22050, 32000),
    OutputFormat("wav_44100", "WAV · 44.1 kHz (Pro+)", "wav", "audio/wav", 44100),
    OutputFormat("wav_48000", "WAV · 48 kHz", "wav", "audio/wav", 48000),
    OutputFormat("wav_24000", "WAV · 24 kHz", "wav", "audio/wav", 24000),
    OutputFormat("pcm_44100", "PCM · 44.1 kHz (Pro+)", "pcm", "audio/L16", 44100),
    OutputFormat("opus_48000_128", "Opus · 48 kHz · 128 kbps", "opus", "audio/ogg", 48000, 128000),
    OutputFormat("ulaw_8000", "μ-law · 8 kHz", "pcm", "audio/basic", 8000),
]

# Fallback capability table when /v1/models cannot be reached during connection tests.
_FALLBACK_MODELS: dict[str, dict[str, Any]] = {
    "eleven_v4": {"style": False, "speaker_boost": True, "max_chars": 10000, "dialogue": True,
                  "language_code": True, "multiplier": 1.0},
    "eleven_v4_turbo": {"style": False, "speaker_boost": True, "max_chars": 10000, "dialogue": True,
                        "language_code": True, "multiplier": 0.5},
    "eleven_v3": {"style": False, "speaker_boost": False, "max_chars": 5000, "dialogue": True,
                  "language_code": True, "multiplier": 1.0},
    "eleven_v3_conversational": {"style": False, "speaker_boost": False, "max_chars": 5000,
                                 "dialogue": True, "language_code": True, "multiplier": 0.5},
    "eleven_multilingual_v2": {"style": True, "speaker_boost": True, "max_chars": 10000,
                               "dialogue": False, "language_code": False, "multiplier": 1.0},
    "eleven_flash_v2_5": {"style": False, "speaker_boost": True, "max_chars": 40000,
                          "dialogue": False, "language_code": True, "multiplier": 0.5},
    "eleven_flash_v2": {"style": False, "speaker_boost": True, "max_chars": 30000,
                        "dialogue": False, "language_code": False, "multiplier": 0.5},
    "eleven_turbo_v2_5": {"style": False, "speaker_boost": True, "max_chars": 40000,
                          "dialogue": False, "language_code": True, "multiplier": 0.5},
}

DEFAULT_VOICES = {
    "narrator": "Rachel · calm narrator",
}

# List-price estimate per character for a standard paid plan (USD). The API reports
# model_rates.character_cost_multiplier, which scales this.
ESTIMATE_USD_PER_CHAR = 0.00012
DIALOGUE_MAX_CHARS = 2000
DIALOGUE_MAX_VOICES = 10


def _mime_for(fmt: str) -> str:
    return next((f.mime for f in OUTPUT_FORMATS if f.id == fmt), "audio/mpeg")


class ElevenLabsProvider:
    name = "elevenlabs"
    label = "ElevenLabs"
    is_mock = False

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        model: str | None = None,
        voice_id: str | None = None,
        output_format: str | None = None,
    ) -> None:
        self._key = api_key
        self._base = (base_url or API_BASE).rstrip("/")
        self.default_model = model or "eleven_multilingual_v2"
        self.default_voice = voice_id
        self.default_format = output_format or "mp3_44100_128"
        self._models_cache: list[dict[str, Any]] | None = None

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self._key, "Accept": "application/json"}

    async def _raw_models(self) -> list[dict[str, Any]]:
        if self._models_cache is not None:
            return self._models_cache

        async def call(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(f"{self._base}/v1/models", headers=self._headers())

        response = await request_with_retry(call, provider=self.label, timeout_s=25)
        payload = _json(response)
        self._models_cache = payload if isinstance(payload, list) else []
        return self._models_cache

    # -- capabilities ------------------------------------------------------
    @staticmethod
    def _capability(model_id: str, raw: dict[str, Any] | None = None) -> dict[str, Any]:
        fallback = _FALLBACK_MODELS.get(model_id, {})
        if raw is None:
            return fallback
        languages = [str(lang.get("language_id")) for lang in raw.get("languages") or []
                     if isinstance(lang, dict) and lang.get("language_id")]
        rates = raw.get("model_rates") or {}
        return {
            "style": bool(raw.get("can_use_style", fallback.get("style", False))),
            "speaker_boost": bool(raw.get("can_use_speaker_boost", fallback.get("speaker_boost", True))),
            "max_chars": int(raw.get("maximum_text_length_per_request") or fallback.get("max_chars") or 10000),
            "dialogue": model_id in {
                "eleven_v3", "eleven_v3_conversational", "eleven_v4", "eleven_v4_turbo",
            } or bool(fallback.get("dialogue")),
            "language_code": model_id not in {"eleven_multilingual_v2", "eleven_flash_v2"},
            "multiplier": float(rates.get("character_cost_multiplier") or fallback.get("multiplier") or 1.0),
            "languages": languages,
            "name": raw.get("name") or model_id,
            "description": raw.get("description"),
        }

    async def test_connection(self) -> TestResult:
        started = time.perf_counter()
        checks: list[dict[str, Any]] = []
        try:
            models = await self._raw_models()
            tts_models = [m for m in models if m.get("can_do_text_to_speech")]
            checks.append({"name": "auth", "ok": True, "detail": "API key accepted"})
            checks.append({
                "name": "models",
                "ok": bool(tts_models),
                "detail": f"{len(tts_models)} text-to-speech model(s) available",
            })
            voices = await self.list_voices()
            checks.append({"name": "voices", "ok": True, "detail": f"{len(voices)} voice(s) visible"})
            ok = all(c["ok"] for c in checks)
            return TestResult(ok, "Connected · models and voices reachable" if ok else "Connected with limits",
                              int((time.perf_counter() - started) * 1000), checks)
        except TTSError as exc:
            checks.append({"name": "auth", "ok": False, "detail": exc.message})
            return TestResult(False, exc.message, int((time.perf_counter() - started) * 1000), checks)

    async def list_models(self) -> list[ModelInfo]:
        try:
            raw_models = await self._raw_models()
        except TTSError:
            raw_models = []
        models: list[ModelInfo] = []
        for raw in raw_models:
            if not raw.get("can_do_text_to_speech"):
                continue
            if raw.get("requires_alpha_access") and not raw.get("can_do_text_to_speech"):
                continue
            model_id = str(raw.get("model_id"))
            cap = self._capability(model_id, raw)
            models.append(ModelInfo(
                id=model_id,
                name=cap["name"],
                description=cap["description"],
                max_chars=cap["max_chars"],
                languages=cap["languages"],
                supports_dialogue=cap["dialogue"],
                deprecated=model_id in {
                    "eleven_turbo_v2", "eleven_turbo_v2_5", "eleven_english_sts_v1",
                    "eleven_english_sts_v2", "eleven_multilingual_sts_v2",
                    "eleven_multilingual_ttv_v2", "eleven_ttv_v3",
                },
            ))
        if not models:
            models = [
                ModelInfo(id=mid, name=mid, max_chars=cap.get("max_chars"),
                          supports_dialogue=cap.get("dialogue"))
                for mid, cap in _FALLBACK_MODELS.items()
            ]
        return models

    async def list_voices(self, *, language: str | None = None, query: str | None = None) -> list[VoiceInfo]:
        voices: list[VoiceInfo] = []
        token: str | None = None
        for _ in range(10):
            params: list[tuple[str, str]] = [
                ("page_size", "100"),
                ("include_total_count", "false"),
            ]
            if token:
                params.append(("next_page_token", token))
            if query:
                params.append(("search", query))
            if language:
                params.append(("language", language))

            async def call(client: httpx.AsyncClient, params=params) -> httpx.Response:
                return await client.get(f"{self._base}/v2/voices", headers=self._headers(), params=params)

            response = await request_with_retry(call, provider=self.label, timeout_s=30)
            page = _json(response)
            for item in page.get("voices") or []:
                labels = item.get("labels") or {}
                voices.append(VoiceInfo(
                    voice_id=item.get("voice_id", ""),
                    name=item.get("name") or "Unnamed voice",
                    language=labels.get("language") or (language or None),
                    locale=labels.get("locale"),
                    gender=labels.get("gender"),
                    category=item.get("category"),
                    description=item.get("description"),
                    preview_url=item.get("preview_url"),
                    labels={k: str(v) for k, v in labels.items()},
                    own_voice=bool(item.get("is_owner")),
                ))
            if not page.get("has_more"):
                break
            token = page.get("next_page_token")
            if not token:
                break
        return voices

    def output_formats(self, model: str) -> list[OutputFormat]:
        return list(OUTPUT_FORMATS)

    def voice_params(self, model: str) -> list[ParamSpec]:
        specs = [ParamSpec("stability", "Stability", "number", 0.0, 1.0, 0.5,
                           help="Higher = more consistent; lower = more expressive.")]
        cap = _FALLBACK_MODELS.get(model, {})
        if cap.get("style", True):
            specs.append(ParamSpec("style", "Style exaggeration", "number", 0.0, 1.0, 0.0,
                                   help="Amplifies the speaker's style; adds latency above 0."))
        if cap.get("speaker_boost", True):
            specs.append(ParamSpec("use_speaker_boost", "Speaker boost", "boolean", None, None, True,
                                   help="Stronger similarity to the original speaker."))
        specs += [
            ParamSpec("speed", "Speed", "number", 0.7, 1.2, 1.0,
                      help="Playback speed supported by current models."),
            ParamSpec("similarity_boost", "Similarity", "number", 0.0, 1.0, 0.75,
                      help="How closely the voice follows the original sample."),
        ]
        return specs

    def language_supported(self, model: str, language: str) -> bool:
        cap = _FALLBACK_MODELS.get(model, {})
        if cap.get("language_code") is False:
            return {"en", "ja", "zh", "de", "hi", "fr", "ko", "pt", "it", "es", "id", "nl", "tr",
                    "fil", "pl", "sv", "bg", "ro", "ar", "cs", "el", "fi", "hr", "ms", "sk", "da",
                    "ta", "uk", "ru"}.issuperset({language.split("-")[0].lower()})
        return True

    def _accepts_language_code(self, model: str) -> bool:
        """``language_code`` exists only for models that advertise it (not multilingual_v2)."""
        return bool(_FALLBACK_MODELS.get(model, {}).get("language_code", True))

    def _voice_settings(self, config: TTSConfig) -> dict[str, Any]:
        cap = _FALLBACK_MODELS.get(config.model, {})
        raw = {k: v for k, v in (config.voice_settings or {}).items() if v is not None}
        settings: dict[str, Any] = {}
        # The text-to-speech endpoint requires all required voice_settings keys from the current
        # schema; defaults match the API reference (stability .5, similarity .75, speed 1).
        settings["stability"] = round(min(max(float(raw.get("stability", 0.5)), 0.0), 1.0), 2)
        settings["similarity_boost"] = round(
            min(max(float(raw.get("similarity_boost", 0.75)), 0.0), 1.0), 2
        )
        if cap.get("style", True):
            settings["style"] = round(min(max(float(raw.get("style", 0.0)), 0.0), 1.0), 2)
        speed = raw.get("speed", config.speed if config.speed is not None else 1.0)
        settings["speed"] = round(min(max(float(speed), 0.7), 1.2), 2)
        if cap.get("speaker_boost", True):
            settings["use_speaker_boost"] = bool(raw.get("use_speaker_boost", True))
        return settings

    # -- generation --------------------------------------------------------
    async def generate_speech(self, config: TTSConfig) -> SynthesisResult:
        if not config.text.strip():
            raise TTSInvalidRequestError("Cannot synthesise an empty text")
        if not config.voice_id:
            raise TTSInvalidRequestError("ElevenLabs requires a voice id")
        model = config.model or self.default_model
        cap = _FALLBACK_MODELS.get(model, {})
        max_chars = int(cap.get("max_chars") or 10000)
        if len(config.text) > max_chars:
            raise TTSInvalidRequestError(
                f"Text is {len(config.text)} characters; model {model} accepts at most {max_chars}. "
                "Split it into chunks."
            )
        fmt = config.output_format or self.default_format
        payload: dict[str, Any] = {
            "text": config.text,
            "model_id": model,
            "voice_settings": self._voice_settings(config),
        }
        language = (config.language or "").split("-")[0]
        if language and self._accepts_language_code(model) and self.language_supported(model, language):
            payload["language_code"] = language
        if config.seed is not None:
            payload["seed"] = int(config.seed) % 4294967296
        if config.prior_text:
            payload["previous_text"] = config.prior_text[-500:]
        if config.next_text:
            payload["next_text"] = config.next_text[:500]

        started = time.perf_counter()

        async def call(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(
                f"{self._base}/v1/text-to-speech/{config.voice_id}",
                headers={**self._headers(), "Content-Type": "application/json", "Accept": "audio/*"},
                params={"output_format": fmt},
                json=payload,
            )

        response = await request_with_retry(call, provider=self.label)
        data = response.content
        mime = _mime_for(fmt)
        audio_tools.validate_audio(data, mime=mime, provider=self.label)
        latency = int((time.perf_counter() - started) * 1000)
        multiplier = float(_FALLBACK_MODELS.get(model, {}).get("multiplier", 1.0))
        return SynthesisResult(
            audio=data,
            mime=mime,
            duration_s=audio_tools.duration_of(data),
            provider=self.name,
            model=model,
            voice_id=config.voice_id,
            output_format=fmt,
            sample_rate=next((f.sample_rate for f in OUTPUT_FORMATS if f.id == fmt), 44100),
            character_count=len(config.text),
            latency_ms=latency,
            estimated_cost_usd=round(len(config.text) * ESTIMATE_USD_PER_CHAR * multiplier, 6),
            request_id=response.headers.get("request-id") or response.headers.get("x-request-id"),
        )

    async def generate_dialogue(self, lines: list[DialogueLine], config: TTSConfig) -> SynthesisResult:
        """Multi-speaker dialogue in one request (official text-to-dialogue endpoint)."""
        if not lines:
            raise TTSInvalidRequestError("Dialogue needs at least one line")
        voices = {line.voice_id for line in lines if line.voice_id}
        if len(voices) > DIALOGUE_MAX_VOICES:
            raise TTSInvalidRequestError(f"Dialogue supports at most {DIALOGUE_MAX_VOICES} voices")
        total = sum(len(line.text) for line in lines)
        if total > DIALOGUE_MAX_CHARS:
            raise TTSInvalidRequestError(
                f"Dialogue is {total} characters; keep it at or below {DIALOGUE_MAX_CHARS} per request"
            )
        model = config.model or "eleven_v3"
        fmt = config.output_format or self.default_format
        settings = self._voice_settings(config)
        payload: dict[str, Any] = {
            "inputs": [{"text": line.text, "voice_id": line.voice_id} for line in lines],
            "model_id": model,
            "settings": {k: v for k, v in settings.items()
                         if k in ("stability", "similarity", "use_speaker_boost")},
        }
        started = time.perf_counter()

        async def call(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(
                f"{self._base}/v1/text-to-dialogue",
                headers={**self._headers(), "Content-Type": "application/json", "Accept": "audio/*"},
                params={"output_format": fmt},
                json=payload,
            )

        response = await request_with_retry(call, provider=self.label)
        data = response.content
        mime = _mime_for(fmt)
        audio_tools.validate_audio(data, mime=mime, provider=self.label)
        return SynthesisResult(
            audio=data,
            mime=mime,
            duration_s=audio_tools.duration_of(data),
            provider=self.name,
            model=model,
            voice_id=",".join(sorted(voices)),
            output_format=fmt,
            sample_rate=next((f.sample_rate for f in OUTPUT_FORMATS if f.id == fmt), 44100),
            character_count=total,
            latency_ms=int((time.perf_counter() - started) * 1000),
            estimated_cost_usd=round(total * ESTIMATE_USD_PER_CHAR * float(
                _FALLBACK_MODELS.get(model, {}).get("multiplier", 1.0)), 6),
            request_id=response.headers.get("request-id"),
        )

    async def voice_preview(self, voice: VoiceInfo) -> bytes | None:
        if not voice.preview_url:
            return None

        async def call(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(voice.preview_url)  # public CDN URL, no key embedded

        try:
            response = await request_with_retry(call, provider=self.label, timeout_s=30, attempts=2)
            return response.content
        except TTSError:
            return None

    # -- port compatibility (legacy TTSProvider.synthesize / voices / health) --------------

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
    ):  # noqa: ANN201 - returns app.ports.interfaces.SynthesizedAudio
        result = await self.generate_speech(TTSConfig(
            text=text,
            voice_id=voice_id or self.default_voice or "",
            model=model or self.default_model,
            language=language,
            output_format=self.default_format,
            voice_settings={"speed": speed},
        ))
        from app.ports.interfaces import SynthesizedAudio, Usage

        return SynthesizedAudio(
            audio=result.audio,
            mime=result.mime,
            duration_s=result.duration_s,
            sample_rate=result.sample_rate,
            usage=Usage(provider=result.provider, model=result.model, operation="tts",
                        units=result.character_count, unit_label="chars",
                        cost_usd=result.estimated_cost_usd, latency_ms=result.latency_ms),
        )

    async def voices(self) -> list[dict]:
        return [
            {"voice_id": v.voice_id, "name": v.name, "language": v.language,
             "description": v.description}
            for v in await self.list_voices()
        ]

    async def health(self) -> tuple[bool, str]:
        result = await self.test_connection()
        return result.ok, result.detail
