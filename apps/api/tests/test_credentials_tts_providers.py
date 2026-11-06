"""Tests for the credential vault and the centralised credential service.

The provider API is simulated at the httpx transport layer, so no network or real key is needed.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import wave

import httpx
import pytest

from app.adapters import tts_cartesia, tts_elevenlabs
from app.core import crypto
from app.core.settings import get_settings
from app.ports.tts import TTSAuthError, TTSInvalidRequestError, TTSRateLimitedError

# --------------------------------------------------------------------------- helpers


def wav_bytes(seconds: float = 0.3, rate: int = 22050) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


class FakeTransport(httpx.AsyncBaseTransport):
    """Routes requests to a handler: ``(method, url, headers, json_body) -> Response``."""

    def __init__(self, handler) -> None:  # type: ignore[no-untyped-def]
        self.handler = handler
        self.requests: list[dict] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = None
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = request.content
        self.requests.append({
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "body": body,
        })
        result = self.handler(request, body)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture()
def wire(monkeypatch):
    """Install a fake transport for requests made through ``tts_http.request_with_retry``."""
    state: dict = {"transport": None}

    original = httpx.AsyncClient

    def factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["transport"] = state["transport"]
        return original(*args, **kwargs)

    monkeypatch.setattr(tts_cartesia.httpx, "AsyncClient", factory)
    monkeypatch.setattr(tts_elevenlabs.httpx, "AsyncClient", factory)
    monkeypatch.setattr("app.adapters.tts_http.asyncio.sleep", _no_sleep)

    def install(handler):  # type: ignore[no-untyped-def]
        transport = FakeTransport(handler)
        state["transport"] = transport
        return transport

    return install


async def _no_sleep(*_args, **_kwargs) -> None:
    return None


# --------------------------------------------------------------------------- vault


def test_aes_gcm_roundtrip_and_scope_binding():
    vault = crypto.CredentialVault(crypto.generate_master_key())
    blob = vault.seal({"api_key": "sk_car_secret"}, aad="provider:a")
    assert blob.startswith(b"v2:")
    assert b"sk_car_secret" not in blob
    assert vault.open(blob, aad="provider:a") == {"api_key": "sk_car_secret"}
    with pytest.raises(crypto.CredentialError):
        vault.open(blob, aad="provider:b")  # ciphertext cannot be transplanted


def test_ciphertext_is_non_deterministic():
    vault = crypto.CredentialVault(crypto.generate_master_key())
    a = vault.seal({"api_key": "x" * 20})
    b = vault.seal({"api_key": "x" * 20})
    assert a != b  # unique nonce per record


def test_missing_or_invalid_master_key_fails_loudly():
    with pytest.raises(crypto.CredentialError) as missing:
        crypto.CredentialVault("")
    assert missing.value.code == "master_key_missing"

    with pytest.raises(crypto.CredentialError) as short:
        crypto.CredentialVault("too-short")
    assert short.value.code == "master_key_invalid"


def test_rejects_key_of_wrong_length_in_base64_form():
    import base64

    with pytest.raises(crypto.CredentialError):
        crypto.CredentialVault(base64.urlsafe_b64encode(b"0123456789").decode())


def test_wrong_key_cannot_open_ciphertext():
    one = crypto.CredentialVault(crypto.generate_master_key())
    two = crypto.CredentialVault(crypto.generate_master_key())
    blob = one.seal({"api_key": "sk-test"})
    with pytest.raises(crypto.CredentialError) as exc:
        two.open(blob)
    assert exc.value.code == "credential_unreadable"


def test_legacy_fernet_payload_is_still_readable():
    from cryptography.fernet import Fernet

    raw, _ = crypto.parse_master_key(crypto.generate_master_key())
    legacy = Fernet(crypto.base64.urlsafe_b64encode(raw)).encrypt(b'{"api_key":"legacy-key"}')
    vault = crypto.CredentialVault(raw)
    assert vault.is_legacy(legacy)
    assert vault.open(legacy) == {"api_key": "legacy-key"}


# --------------------------------------------------------------------------- credentials API


def test_credential_crud_is_masked_and_audited(client, auth):
    base = "/api/v1/providers/tts/cartesia"
    resp = client.post(f"{base}/credentials", json={"api_key": "sk_car_" + "a" * 40})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_credential"] is True
    assert body["status"] == "active"
    assert body["version"] == 1
    assert "sk_car_" not in resp.text.replace(body["fingerprint"], "")
    assert body["fingerprint"].startswith("sk_")

    # empty input must not overwrite
    blank = client.post(f"{base}/credentials", json={"api_key": ""})
    assert blank.status_code == 200
    assert blank.json()["version"] == 1

    rotated = client.post(f"{base}/credentials", json={"api_key": "sk_car_" + "b" * 40})
    assert rotated.json()["version"] == 2
    assert rotated.json()["fingerprint"] == crypto.CredentialVault.fingerprint("sk_car_" + "b" * 40)

    removed = client.delete(f"{base}/credentials")
    assert removed.status_code == 200
    assert removed.json()["has_credential"] is False
    assert removed.json()["status"] == "disabled"

    audit = client.get("/api/v1/workspace/audit", params={"limit": 50}).json()
    actions = [row["action"] for row in audit]
    assert "provider.credentials.updated" in actions
    assert "provider.credentials.removed" in actions


def test_credential_requires_admin(client, auth):
    created = client.post(
        "/api/v1/workspace/members",
        json={"email": "viewer@factory.app", "name": "Viewer", "role": "viewer",
              "password": "viewer-password-123"},
    )
    if created.status_code not in (200, 201, 409):
        pytest.skip(f"cannot create member: {created.text}")
    viewer = httpx.Client(base_url="http://testserver", transport=client._transport,
                          follow_redirects=True)
    login = viewer.post("/api/v1/auth/login",
                        json={"email": "viewer@factory.app", "password": "viewer-password-123"})
    assert login.status_code == 200, login.text
    resp = viewer.post("/api/v1/providers/tts/elevenlabs/credentials",
                       json={"api_key": "xi-" + "c" * 30})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"
    # readable providers list is still allowed for viewers
    assert viewer.get("/api/v1/providers").status_code == 200


def test_master_key_status_endpoint(client):
    body = client.get("/api/v1/providers/encryption").json()
    assert body["ready"] is True
    assert body["algorithm"] == "AES-256-GCM"


def test_cache_invalidation_on_update():
    from app.services.credentials import _CACHE, invalidate

    _CACHE["abc"] = None  # type: ignore[assignment]
    invalidate("abc")
    assert "abc" not in _CACHE


# --------------------------------------------------------------------------- Cartesia


def _cartesia_ok(request, body):
    if request.url.path == "/voices":
        return httpx.Response(200, json={"data": [
            {"id": "voice-1", "name": "Skylar", "description": "Warm", "language": "en",
             "is_owner": False, "status": "active", "access": "public", "visibility": "all",
             "tagline": "", "created_at": "2026-01-01T00:00:00Z",
             "accents": [{"accent": "general-american", "locale": "en-US", "is_native": True}]},
        ], "has_more": False})
    return httpx.Response(200, content=wav_bytes(), headers={"content-type": "audio/wav"})


def test_cartesia_connection_and_voices(wire):
    transport = wire(_cartesia_ok)
    provider = tts_cartesia.CartesiaProvider("sk_car_test")

    result = asyncio.run(provider.test_connection())
    assert result.ok is True
    assert transport.requests[0]["headers"]["authorization"] == "Bearer sk_car_test"
    assert transport.requests[0]["headers"]["cartesia-version"] == tts_cartesia.API_VERSION

    voices = asyncio.run(provider.list_voices())
    assert voices[0].voice_id == "voice-1"
    assert voices[0].locale == "en-US"


def test_cartesia_generation_uses_documented_payload(wire):
    transport = wire(_cartesia_ok)
    provider = tts_cartesia.CartesiaProvider("sk_car_test")
    from app.ports.tts import TTSConfig

    result = asyncio.run(provider.generate_speech(TTSConfig(
        text="Hello there.", voice_id="voice-1", model="sonic-3.6", language="en",
        output_format="mp3/44100/128000", voice_settings={"speed": 2.5, "volume": 1.2},
    )))
    post = next(r for r in transport.requests if r["method"] == "POST")
    assert post["url"].endswith("/tts/bytes")
    assert post["body"]["model_id"] == "sonic-3.6"
    assert post["body"]["voice"] == {"id": "voice-1"}
    assert post["body"]["language"] == "en"
    assert "locale" not in post["body"]
    assert post["body"]["output_format"] == {"container": "mp3", "sample_rate": 44100,
                                             "bit_rate": 128000}
    assert post["body"]["generation_config"]["speed"] == 1.5  # clamped to the documented range
    assert result.provider == "cartesia"
    assert result.character_count == len("Hello there.")
    assert result.estimated_cost_usd > 0


def test_cartesia_rejects_unknown_model():
    provider = tts_cartesia.CartesiaProvider("sk_car_test")
    from app.ports.tts import TTSConfig

    with pytest.raises(TTSInvalidRequestError):
        asyncio.run(provider.generate_speech(TTSConfig(text="hi", voice_id="v", model="sonic-2")))


def test_cartesia_invalid_key_and_rate_limit(wire):
    wire(lambda request, body: httpx.Response(401, json={"message": "invalid api key"}))
    provider = tts_cartesia.CartesiaProvider("sk_car_bad")
    result = asyncio.run(provider.test_connection())
    assert result.ok is False

    calls = {"n": 0}

    def limited(request, body):
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "0"}, json={"message": "slow down"})

    transport = wire(limited)
    from app.ports.tts import TTSConfig

    with pytest.raises(TTSRateLimitedError):
        asyncio.run(provider.generate_speech(TTSConfig(text="hi", voice_id="v",
                                                       model="sonic-3.6")))
    assert len(transport.requests) == get_settings().tts_max_attempts


def test_cartesia_timeout_is_transient(wire):
    wire(lambda request, body: httpx.ConnectTimeout("timed out"))
    provider = tts_cartesia.CartesiaProvider("sk_car_test")
    from app.ports.tts import TTSTransientError

    with pytest.raises(TTSTransientError):
        asyncio.run(provider.generate_speech(
            __import__("app.ports.tts", fromlist=["TTSConfig"]).TTSConfig(
                text="hi", voice_id="v", model="sonic-3.6")))


# --------------------------------------------------------------------------- ElevenLabs


def _eleven_ok(request, body):
    path = request.url.path
    if path == "/v1/models":
        return httpx.Response(200, json=[
            {"model_id": "eleven_multilingual_v2", "name": "Multilingual v2",
             "can_do_text_to_speech": True, "can_use_style": True,
             "can_use_speaker_boost": True, "maximum_text_length_per_request": 10000,
             "languages": [{"language_id": "en", "name": "English"}],
             "model_rates": {"character_cost_multiplier": 1.0}},
            {"model_id": "eleven_flash_v2_5", "name": "Flash v2.5",
             "can_do_text_to_speech": True, "can_use_style": False,
             "maximum_text_length_per_request": 40000,
             "model_rates": {"character_cost_multiplier": 0.5}},
        ])
    if path == "/v2/voices":
        return httpx.Response(200, json={"voices": [
            {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George", "category": "premade",
             "labels": {"language": "en", "gender": "male"}, "preview_url": "https://cdn/x.mp3"},
        ], "has_more": False, "total_count": 1})
    if path == "/v1/text-to-dialogue":
        return httpx.Response(200, content=wav_bytes(), headers={"content-type": "audio/wav"})
    return httpx.Response(200, content=wav_bytes(), headers={"content-type": "audio/wav"})


def test_elevenlabs_models_voices_and_generation(wire):
    transport = wire(_eleven_ok)
    provider = tts_elevenlabs.ElevenLabsProvider("xi-test")

    models = asyncio.run(provider.list_models())
    assert {m.id for m in models} == {"eleven_multilingual_v2", "eleven_flash_v2_5"}
    assert transport.requests[0]["headers"]["xi-api-key"] == "xi-test"

    voices = asyncio.run(provider.list_voices())
    assert voices[0].voice_id == "JBFqnCBsd6RMkjVDRZzb"
    assert transport.requests[-1]["url"].startswith("https://api.elevenlabs.io/v2/voices")

    from app.ports.tts import TTSConfig

    result = asyncio.run(provider.generate_speech(TTSConfig(
        text="Hello.", voice_id="JBFqnCBsd6RMkjVDRZzb", model="eleven_multilingual_v2",
        language="fr", output_format="mp3_44100_192",
        voice_settings={"stability": 0.3, "style": 0.4, "speed": 1.1},
    )))
    post = next(r for r in transport.requests if r["method"] == "POST")
    assert "/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb" in post["url"]
    assert "output_format=mp3_44100_192" in post["url"]
    assert post["body"]["model_id"] == "eleven_multilingual_v2"
    assert post["body"]["voice_settings"]["stability"] == 0.3
    assert post["body"]["voice_settings"]["style"] == 0.4
    # multilingual_v2 does not accept language_code — it must not be sent
    assert "language_code" not in post["body"]
    assert result.output_format == "mp3_44100_192"


def test_elevenlabs_hides_unsupported_voice_settings():
    provider = tts_elevenlabs.ElevenLabsProvider("xi-test")
    keys = {p.key for p in provider.voice_params("eleven_flash_v2_5")}
    assert "style" not in keys
    assert "stability" in keys
    assert "use_speaker_boost" in keys


def test_elevenlabs_dialogue(wire):
    transport = wire(_eleven_ok)
    provider = tts_elevenlabs.ElevenLabsProvider("xi-test")
    from app.ports.tts import DialogueLine, TTSConfig

    result = asyncio.run(provider.generate_dialogue(
        [DialogueLine("[whispering] Knock knock", "v1"), DialogueLine("Who is there?", "v2")],
        TTSConfig(text="", voice_id="", model="eleven_v3"),
    ))
    post = next(r for r in transport.requests if r["method"] == "POST")
    assert post["url"].startswith("https://api.elevenlabs.io/v1/text-to-dialogue")
    assert [i["voice_id"] for i in post["body"]["inputs"]] == ["v1", "v2"]
    assert post["body"]["model_id"] == "eleven_v3"
    assert result.provider == "elevenlabs"


def test_elevenlabs_dialogue_rejects_oversized_requests():
    provider = tts_elevenlabs.ElevenLabsProvider("xi-test")
    from app.ports.tts import DialogueLine, TTSConfig

    with pytest.raises(TTSInvalidRequestError):
        asyncio.run(provider.generate_dialogue(
            [DialogueLine("x" * 2500, "v")], TTSConfig(text="", voice_id="", model="eleven_v3")))


def test_elevenlabs_invalid_key_and_text_limit(wire):
    wire(lambda request, body: httpx.Response(401, json={"detail": {"message": "bad key"}}))
    provider = tts_elevenlabs.ElevenLabsProvider("xi-bad")
    from app.ports.tts import TTSConfig

    with pytest.raises(TTSAuthError):
        asyncio.run(provider.generate_speech(TTSConfig(text="hi", voice_id="v",
                                                       model="eleven_multilingual_v2")))
    with pytest.raises(TTSInvalidRequestError):
        asyncio.run(provider.generate_speech(TTSConfig(text="x" * 10001, voice_id="v",
                                                       model="eleven_multilingual_v2")))


def test_error_text_never_echoes_the_api_key(wire):
    secret = "sk_car_" + "s" * 30

    def echo(request, body):
        return httpx.Response(401, json={"message": f"invalid key {secret}"})

    wire(echo)
    provider = tts_cartesia.CartesiaProvider(secret)
    from app.ports.tts import TTSConfig

    with pytest.raises(TTSAuthError) as exc:
        asyncio.run(provider.generate_speech(TTSConfig(text="hi", voice_id="v",
                                                       model="sonic-3.6")))
    assert secret not in str(exc.value)
    assert "[redacted]" in str(exc.value)


# --------------------------------------------------------------------------- misc


def test_env_prefers_app_encryption_key(monkeypatch):
    key = crypto.generate_master_key()
    monkeypatch.setenv("APP_ENCRYPTION_KEY", key)
    get_settings.cache_clear()
    try:
        assert get_settings().app_encryption_key == key
        assert os.environ["APP_ENCRYPTION_KEY"] == key
    finally:
        get_settings.cache_clear()
