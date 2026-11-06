"""Cartesia Sonic adapter — the official ``POST /tts/bytes`` API.

Verified against the current OpenAPI spec (``latest.yml``), Cartesia-Version ``2026-08-14``:

* Auth: ``Authorization: Bearer <api key>`` (``sk_car_…``) plus the required ``Cartesia-Version``
  header. The only accepted version today is ``2026-08-14``.
* Body: ``model_id`` (``sonic-3.6`` | ``sonic-3.5`` | ``sonic-3`` | ``sonic-latest``),
  ``transcript``, ``voice`` (id string or ``{id}``), ``output_format`` (WAV / MP3 / raw with an
  enumerated sample-rate list), optional ``language`` **or** ``locale`` (never both) and
  ``generation_config`` ({volume, speed, emotion}) which only exists on ``sonic-3`` and newer.
* ``GET /voices`` is cursor-paginated and can expand ``preview_file_url``; preview files need the
  same bearer token, so they are proxied rather than linked.

The model list is not exposed by the API; ``MODELS`` below mirrors
docs.cartesia.ai/build-with-cartesia/tts-models and is the single place to update when Cartesia
ships a new model. Nothing else in the codebase knows about model ids.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import httpx

from app.adapters import audio as audio_tools
from app.adapters.tts_http import _json, request_with_retry, wrap_transport
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

log = get_logger("factory.tts.cartesia")

API_BASE = "https://api.cartesia.ai"
API_VERSION = "2026-08-14"  # the only value accepted by the API today

SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)
MP3_BIT_RATES = (32000, 64000, 96000, 128000, 192000)
ENCODINGS = (
    ("pcm_s16le", "PCM 16-bit"),
    ("pcm_f32le", "PCM 32-bit float"),
    ("pcm_mulaw", "μ-law"),
    ("pcm_alaw", "A-law"),
)

MODELS: list[ModelInfo] = [
    ModelInfo(
        id="sonic-3.6",
        name="Sonic 3.6",
        description="Most natural and expressive model; 44 languages, emotion and speed control.",
        max_chars=None,
        supports_dialogue=False,
        languages=[
            "en", "fr", "de", "es", "pt", "zh", "ja", "hi", "it", "ko", "nl", "pl", "ru", "sv",
            "tr", "tl", "bg", "ro", "ar", "cs", "el", "fi", "hr", "ms", "sk", "da", "ta", "uk",
            "hu", "no", "vi", "bn", "th", "he", "ka", "id", "te", "gu", "kn", "ml", "mr", "pa",
            "or", "ur",
        ],
    ),
    ModelInfo(id="sonic-3.5", name="Sonic 3.5", description="Previous generation; same API surface.",
              languages=["en", "fr", "de", "es", "pt", "zh", "ja", "hi", "it", "ko", "nl", "pl",
                         "ru", "sv", "tr", "tl", "bg", "ro", "ar", "cs", "el", "fi", "hr", "ms",
                         "sk", "da", "ta", "uk", "hu", "no", "vi"]),
    ModelInfo(id="sonic-3", name="Sonic 3", description="Stable 3.x model.",
              languages=["en", "fr", "de", "es", "pt", "zh", "ja", "hi", "it", "ko", "nl", "pl",
                         "ru", "sv", "tr"]),
    ModelInfo(id="sonic-latest", name="Sonic (latest alias)",
              description="Always points at the newest stable snapshot."),
]

EMOTIONS = (
    "neutral", "happy", "excited", "enthusiastic", "calm", "content", "curious", "sad",
    "angry", "scared", "mysterious", "proud", "confident", "determined", "nostalgic",
    "apologetic", "anxious", "surprised", "grateful",
)

_SUPPORTED: dict[str, dict[str, Any]] = {
    # generation_config volume/speed/emotion exist on sonic-3 and newer (docs: "Available on
    # sonic-3 and newer models; not available on earlier models").
    "sonic-3.6": {"config": True, "max_speed": 1.5, "min_speed": 0.6},
    "sonic-3.5": {"config": True, "max_speed": 1.5, "min_speed": 0.6},
    "sonic-3": {"config": True, "max_speed": 1.5, "min_speed": 0.6},
    "sonic-latest": {"config": True, "max_speed": 1.5, "min_speed": 0.6},
}

# list-price estimate; Cartesia bills ~1 credit per character (see docs/pricing). Replace through
# the provider's model pricing instead of editing this when a real contract rate exists.
ESTIMATE_USD_PER_CHAR = 0.000065


def format_id(container: str, sample_rate: int, *, encoding: str = "pcm_s16le",
              bit_rate: int = 128000) -> str:
    if container == "mp3":
        return f"mp3/{sample_rate}/{bit_rate}"
    if container == "raw":
        return f"raw/{sample_rate}/{encoding}"
    return f"wav/{sample_rate}/{encoding}"


def parse_format(value: str | dict[str, Any] | None, sample_rate_hint: int | None = None) -> dict[str, Any]:
    """Accept ``wav/44100/pcm_s16le``, ``mp3/44100/128000`` or a compatible dict."""
    if isinstance(value, dict):
        return value
    parts = (value or "").split("/")
    container = parts[0] or "wav"
    rate = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else (sample_rate_hint or 44100)
    if container == "mp3":
        return {"container": "mp3", "sample_rate": rate, "bit_rate": int(parts[2]) if len(parts) > 2 else 128000}
    if container == "raw":
        return {"container": "raw", "sample_rate": rate, "encoding": parts[2] if len(parts) > 2 else "pcm_s16le"}
    return {"container": "wav", "sample_rate": rate, "encoding": parts[2] if len(parts) > 2 else "pcm_s16le"}


def simulate_format(fmt: dict[str, Any]) -> OutputFormat:
    container = fmt.get("container", "wav")
    encoding = fmt.get("encoding", "pcm_s16le")
    rate = int(fmt.get("sample_rate", 44100))
    bit_rate = fmt.get("bit_rate")
    mime = {"wav": "audio/wav", "mp3": "audio/mpeg", "raw": "audio/L16"}.get(container, "application/octet-stream")
    fid = format_id(container, rate, encoding=encoding, bit_rate=int(bit_rate or 128000))
    label = f"{container.upper()} · {rate / 1000:g} kHz"
    if container == "mp3":
        label += f" · {int(bit_rate or 128000) // 1000} kbps"
    return OutputFormat(
        id=fid, label=label, container=container, mime=mime, sample_rate=rate,
        bit_rate=int(bit_rate) if bit_rate else None, encoding=encoding,
    )


class CartesiaProvider:
    name = "cartesia"
    label = "Cartesia"
    is_mock = False

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        api_version: str = API_VERSION,
        model: str | None = None,
        voice_id: str | None = None,
        output_format: str | None = None,
    ) -> None:
        self._key = api_key
        self._base = (base_url or API_BASE).rstrip("/")
        self._version = api_version or API_VERSION
        self.default_model = model or "sonic-3.6"
        self.default_voice = voice_id
        self.default_format = output_format or format_id("wav", 44100)

    # -- http --------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._key}",
            "Cartesia-Version": self._version,
            "Accept": "application/json",
        }

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async def call(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(f"{self._base}{path}", headers=self._headers(), params=params)

        response = await request_with_retry(call, provider=self.label, timeout_s=25)
        return _json(response)

    # -- introspection -----------------------------------------------------
    async def test_connection(self) -> TestResult:
        started = time.perf_counter()
        checks: list[dict[str, Any]] = []
        try:
            page = await self._get_json("/voices", {"limit": 1})
            voices = page.get("data") or []
            checks.append({"name": "auth", "ok": True, "detail": "API key accepted"})
            checks.append({
                "name": "voices",
                "ok": True,
                "detail": f"{len(voices)} voice(s) visible on this page",
            })
            version = self._version
            if version != API_VERSION:
                checks.append({
                    "name": "api_version",
                    "ok": False,
                    "detail": f"Configured version {version}; API currently accepts {API_VERSION}",
                })
            ok = all(c["ok"] for c in checks)
            return TestResult(
                ok=ok,
                detail="Connected · voices reachable" if ok else "Connected, but the API version is stale",
                latency_ms=int((time.perf_counter() - started) * 1000),
                checks=checks,
            )
        except TTSError as exc:
            checks.append({"name": "auth", "ok": False, "detail": exc.message})
            return TestResult(False, exc.message, int((time.perf_counter() - started) * 1000), checks)

    async def list_models(self) -> list[ModelInfo]:
        return list(MODELS)

    async def list_voices(self, *, language: str | None = None, query: str | None = None) -> list[VoiceInfo]:
        voices: list[VoiceInfo] = []
        cursor: str | None = None
        for _ in range(10):  # 10 pages × 100 = 1000 voices — enough for a picker
            params: dict[str, Any] = {"limit": 100, "expand[]": "preview_file_url"}
            if cursor:
                params["starting_after"] = cursor
            if language:
                params["language"] = language
            if query:
                params["q"] = query
            page = await self._get_json("/voices", params)
            for item in page.get("data") or []:
                accents = item.get("accents") or []
                native = next((a for a in accents if a.get("is_native")), None) or (accents[0] if accents else None)
                voices.append(
                    VoiceInfo(
                        voice_id=item.get("id", ""),
                        name=item.get("name") or "Unnamed voice",
                        language=(native or {}).get("locale", "").split("-")[0] or item.get("language"),
                        locale=(native or {}).get("locale") or item.get("country"),
                        gender=item.get("gender"),
                        category="pro" if item.get("is_pro") else ("own" if item.get("is_owner") else "library"),
                        description=item.get("description") or item.get("tagline") or None,
                        preview_url=item.get("preview_file_url"),
                        labels={a.get("accent", ""): a.get("locale", "") for a in accents if a.get("accent")},
                        own_voice=bool(item.get("is_owner")),
                    )
                )
            if not page.get("has_more"):
                break
            cursor = page.get("next_page")
            if not cursor:
                break
        return voices

    def output_formats(self, model: str) -> list[OutputFormat]:
        formats = [simulate_format({"container": "wav", "sample_rate": rate, "encoding": enc})
                   for rate in (44100, 48000) for enc in ("pcm_s16le",)]
        formats += [
            simulate_format({"container": "wav", "sample_rate": 24000, "encoding": "pcm_s16le"}),
            simulate_format({"container": "mp3", "sample_rate": 44100, "bit_rate": 128000}),
            simulate_format({"container": "mp3", "sample_rate": 44100, "bit_rate": 192000}),
            simulate_format({"container": "mp3", "sample_rate": 48000, "bit_rate": 128000}),
            simulate_format({"container": "mp3", "sample_rate": 22050, "bit_rate": 32000}),
        ]
        return formats

    def voice_params(self, model: str) -> list[ParamSpec]:
        spec = _SUPPORTED.get(model, _SUPPORTED["sonic-latest"])
        if not spec["config"]:
            return []
        return [
            ParamSpec("speed", "Speed", "number", spec["min_speed"], spec["max_speed"], 1.0,
                      help="0.6×–1.5× playback speed (sonic-3 and newer)."),
            ParamSpec("volume", "Volume", "number", 0.5, 2.0, 1.0,
                      help="0.5×–2.0× output gain."),
            ParamSpec("emotion", "Emotion", "enum", None, None, "",
                      options=[{"value": "", "label": "auto (from transcript)"}]
                      + [{"value": e, "label": e} for e in EMOTIONS],
                      help="Guides delivery; leave on auto to infer from the text."),
        ]

    def language_supported(self, model: str, language: str) -> bool:
        info = next((m for m in MODELS if m.id == model), None)
        if info is None or not info.languages:
            return True
        return language.split("-")[0].lower() in info.languages

    # -- generation --------------------------------------------------------
    async def generate_speech(self, config: TTSConfig) -> SynthesisResult:
        if not config.text.strip():
            raise TTSInvalidRequestError("Cannot synthesise an empty text")
        if not config.voice_id:
            raise TTSInvalidRequestError("Cartesia requires a voice id")
        model = config.model or self.default_model
        spec = _SUPPORTED.get(model)
        if spec is None:
            raise TTSInvalidRequestError(f"Unsupported Cartesia model '{model}'")
        fmt = parse_format(config.output_format or self.default_format)
        if int(fmt.get("sample_rate", 44100)) not in SAMPLE_RATES:
            raise TTSInvalidRequestError(f"Unsupported sample rate {fmt.get('sample_rate')}")
        payload: dict[str, Any] = {
            "model_id": model,
            "transcript": config.text,
            "voice": {"id": config.voice_id},
            "output_format": fmt,
        }
        language = config.language or "en"
        if language:
            payload["language"] = language  # never send 'locale' as well — that is a 400
        generation: dict[str, Any] = {}
        settings = {k: v for k, v in (config.voice_settings or {}).items() if v not in (None, "")}
        if spec["config"]:
            speed = settings.get("speed", config.speed)
            if speed is not None:
                generation["speed"] = float(min(max(float(speed), spec["min_speed"]), spec["max_speed"]))
            if settings.get("volume") is not None:
                generation["volume"] = float(min(max(float(settings["volume"]), 0.5), 2.0))
            emotion = settings.get("emotion") or config.emotion
            if emotion:
                generation["emotion"] = emotion
        elif settings:
            log.info("cartesia.ignoring_unsupported_settings model=%s keys=%s", model, list(settings))
        if generation:
            payload["generation_config"] = generation

        started = time.perf_counter()

        async def call(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(
                f"{self._base}/tts/bytes",
                headers={**self._headers(), "Content-Type": "application/json", "Accept": "audio/*"},
                json=payload,
            )

        try:
            response = await request_with_retry(call, provider=self.label)
        except TTSError:
            raise
        except Exception as exc:  # noqa: BLE001 - transport errors become typed TTS errors
            raise wrap_transport(exc, self.label) from exc
        latency = int((time.perf_counter() - started) * 1000)
        data = response.content
        mime = "audio/mpeg" if fmt["container"] == "mp3" else (
            "audio/L16" if fmt["container"] == "raw" else "audio/wav"
        )
        audio_tools.validate_audio(data, mime=mime, provider=self.label)
        duration = audio_tools.duration_of(data) if fmt["container"] != "raw" else 0.0
        if fmt["container"] == "raw":
            # headerless PCM: infer length from bytes
            duration = round(len(data) / 2 / int(fmt["sample_rate"]), 2)
        return SynthesisResult(
            audio=data,
            mime=mime,
            duration_s=duration,
            provider=self.name,
            model=model,
            voice_id=config.voice_id,
            output_format=format_id(fmt["container"], int(fmt["sample_rate"]),
                                    encoding=fmt.get("encoding", "pcm_s16le"),
                                    bit_rate=int(fmt.get("bit_rate", 128000))),
            sample_rate=int(fmt["sample_rate"]),
            character_count=len(config.text),
            latency_ms=latency,
            estimated_cost_usd=round(len(config.text) * ESTIMATE_USD_PER_CHAR, 6),
            request_id=response.headers.get("x-request-id"),
            warnings=[] if spec["config"] else [],
        )

    async def generate_dialogue(self, lines: list[DialogueLine], config: TTSConfig) -> SynthesisResult:
        raise TTSInvalidRequestError(
            "Cartesia does not expose a multi-speaker dialogue endpoint; use one request per "
            "speaker and combine the clips."
        )

    async def voice_preview(self, voice: VoiceInfo) -> bytes | None:
        if not voice.preview_url:
            return None
        url = voice.preview_url
        path = url[len(self._base):] if url.startswith(self._base) else url

        async def call(client: httpx.AsyncClient) -> httpx.Response:
            if path.startswith("http"):
                return await client.get(url, headers={"Authorization": f"Bearer {self._key}"})
            return await client.get(f"{self._base}{quote(path)}", headers={
                "Authorization": f"Bearer {self._key}", "Cartesia-Version": self._version,
            })

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
            voice_settings={"speed": speed, **({"emotion": emotion} if emotion else {})},
        ))
        return _legacy_audio(result)

    async def voices(self) -> list[dict]:
        return [
            {"voice_id": v.voice_id, "name": v.name, "language": v.language,
             "description": v.description}
            for v in await self.list_voices()
        ]

    async def health(self) -> tuple[bool, str]:
        result = await self.test_connection()
        return result.ok, result.detail


def _legacy_audio(result: SynthesisResult):  # noqa: ANN202
    """Adapt a SynthesisResult to the port-level SynthesizedAudio dataclass."""
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
