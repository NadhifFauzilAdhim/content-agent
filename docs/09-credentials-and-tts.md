# 09 · Credentials & Text-to-Speech

How provider credentials are stored, how Cartesia and ElevenLabs are integrated, and how the Audio
Studio and the Voice Agent use them.

---

## 1. Centralised credential management

### Where to configure

**Providers → Text to speech → (Cartesia | ElevenLabs) → add key / manage key.**

The same editor is used for every provider kind (LLM, TTS, image), so a new integration never
needs a second credential system. Fields:

| Field | Meaning |
| --- | --- |
| `api_key` | The provider key. Masked input, never echoed back. |
| `default_model` | Inherited model unless a channel/workflow/scene overrides it (TTS only). |
| `default_voice_id` | Inherited voice (TTS only). |
| `default_output_format` | Provider-native format id (TTS only). |

### Endpoints

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/v1/providers/encryption` | any member — is the master key usable? |
| `GET` | `/api/v1/providers/{kind}/{slug}/credentials` | admin — metadata only |
| `POST` | `/api/v1/providers/{kind}/{slug}/credentials` | admin — merge (empty values ignored) |
| `PUT` | `/api/v1/providers/{kind}/{slug}/credentials` | admin — rotate (key required) |
| `DELETE` | `/api/v1/providers/{kind}/{slug}/credentials` | admin — shred the stored key |
| `POST` | `/api/v1/providers/{id}/test` | editor — live connection test |

A credential response looks like this — there is no field that can carry the secret:

```json
{
  "provider": "cartesia", "kind": "tts", "has_credential": true, "status": "active",
  "version": 3, "fingerprint": "sk_…a91f", "fields": ["api_key"],
  "readable": true, "problem": null, "encryption_ready": true
}
```

### Encryption

* **AES-256-GCM** (`cryptography` `AESGCM`), a fresh 96-bit nonce per record.
* Additional authenticated data = `provider:<workspace>:<provider id>`, so a blob copied to another
  row fails authentication instead of decrypting to the wrong provider.
* Blob layout: `b"v2:" + nonce + ciphertext+tag`.
* Master key: `APP_ENCRYPTION_KEY` (64 hex characters or 32 base64 bytes). `CREDENTIAL_KEY` is
  still read when the new name is unset, so existing installations keep working; old Fernet blobs
  are re-sealed with AES-GCM on first read.
* A missing/invalid key **never** falls back to plaintext: writes return a validation error and the
  providers page shows a setup state.

Generate a key once:

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m app.cli gen-key
```

### Rotation without restart

Writes bump `ai_providers.credential_version`, replace the in-process cache entry and set
`credential_status='active'`. Adapters read through `CredentialService.get_secret()`, which returns
a 60-second cached copy keyed by version. Long-running work can pass `expected_version` so it keeps
the configuration it started with and logs when a rotation happened mid-run.

### Audit

Every create, rotate, remove and settings change writes an `audit_logs` row with the actor, action
(`provider.credentials.updated`, `provider.credentials.removed`, `tts.settings.updated`,
`channel.voice.updated`), the field names, the new fingerprint and the version. Values never appear
in audit rows, logs or API errors (HTTP error text is redacted for `sk_…`, `xi-…`, `Bearer …` and
`api_key=` patterns).

---

## 2. Provider adapters

Both adapters implement the same interface (`app/ports/tts_provider.py`):

```python
class TTSProvider(Protocol):
    async def test_connection(self) -> TestResult: ...
    async def list_models(self) -> list[ModelInfo]: ...
    async def list_voices(self, *, language=None, query=None) -> list[VoiceInfo]: ...
    def output_formats(self, model: str) -> list[OutputFormat]: ...
    def voice_params(self, model: str) -> list[ParamSpec]: ...
    def language_supported(self, model: str, language: str) -> bool: ...
    async def generate_speech(self, config: TTSConfig) -> SynthesisResult: ...
    async def generate_dialogue(self, lines, config) -> SynthesisResult: ...
    async def voice_preview(self, voice) -> bytes | None: ...
```

### Cartesia (`app/adapters/tts_cartesia.py`)

Verified against the current API reference (Cartesia-Version `2026-08-14`):

* `POST https://api.cartesia.ai/tts/bytes`, header `Authorization: Bearer <key>` plus
  `Cartesia-Version`.
* Models: `sonic-3.6`, `sonic-3.5`, `sonic-3`, `sonic-latest`. The API does not publish a models
  endpoint, so the catalogue lives in `MODELS` in the adapter — the single place to update.
* `output_format` is an object: `{container: wav|mp3|raw, sample_rate, encoding, bit_rate}`.
* `generation_config` (`speed` 0.6–1.5, `volume` 0.5–2.0, `emotion`) only exists on `sonic-3` and
  newer — the UI hides those controls for older models and the adapter drops them.
* `language` **or** `locale`, never both (sending both is a 400).
* `GET /voices` is cursor-paginated; `expand[]=preview_file_url` returns preview files that need
  the bearer token, so previews are proxied through the API.

### ElevenLabs (`app/adapters/tts_elevenlabs.py`)

* `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`, header `xi-api-key`,
  `?output_format=mp3_44100_128` style.
* `GET /v1/models` is the source of truth: only models with `can_do_text_to_speech` are listed, and
  `can_use_style` / `can_use_speaker_boost` / `maximum_text_length_per_request` /
  `model_rates.character_cost_multiplier` drive the UI and cost estimate.
* `language_code` is sent only for models that accept it (`eleven_multilingual_v2` does not).
* `GET /v2/voices` (paginated, searchable) feeds the picker; previews are public CDN files.
* Dialogue: `POST /v1/text-to-dialogue` with up to 10 voices and ~2,000 characters per request.

### Error handling

`app/adapters/tts_http.py` is shared by both adapters:

| Condition | Exception | Retried |
| --- | --- | --- |
| connect/read timeout, network error | `TTSTransientError` | yes (backoff + jitter) |
| 429 | `TTSRateLimitedError` (honours `Retry-After`) | yes |
| 5xx | `TTSTransientError` | yes |
| 401/403 | `TTSAuthError` | no |
| 400/404/422 | `TTSInvalidRequestError` | no |

Retries are owned by the adapter (`TTS_MAX_ATTEMPTS`, default 3). Inside a voice-agent narration,
each *chunk* is retried by the agent (`tts_retries`, default 2) so a single failed chunk is
regenerated without repeating the whole narration.

---

## 3. Configuration inheritance

Resolution happens in `TTSConfigurationService.resolve()` and the answer is inspectable:

```powershell
curl -H "authorization: Bearer $TOKEN" http://127.0.0.1:8001/api/v1/tts/debug/resolved
```

```json
{
  "provider": "cartesia", "model": "sonic-3.6", "voice_id": "db6b0ed5-…",
  "language": "en", "output_format": "wav/44100/pcm_s16le",
  "sources": {"provider": "global", "model": "global", "voice_id": "channel"},
  "chain": [{"level": "global", "values": {...}}, {"level": "channel", "values": {...}}]
}
```

Order (least specific first): **workspace default → channel → workflow → scene → request**.
Anything unset inherits; a value equal to a field default still counts as an override.

| Scope | Stored in | Edited at |
| --- | --- | --- |
| workspace | `tts_configurations` | Settings → Voice defaults |
| channel | `channel_settings.voice_provider/voice_id/voice_model/voice_config` | API `PUT /api/v1/tts/channels/{id}` |
| workflow | `production_workflows.input_json.voice` | API when starting a run |
| scene | voice agent payload | API / agents |

### Fallback

Set a fallback provider in Settings → Voice defaults. Fallback happens **only** for transient
failures (timeouts, 5xx, exhausted rate limits). Invalid keys, unknown voice ids and malformed
requests are reported immediately — they would fail on the fallback too. The generation record keeps
`fallback_used`, `fallback_from` and the reason, and every audio asset stores the provider that
actually produced it.

---

## 4. Generation, chunking and storage

* Text is split on paragraph → sentence → clause → word boundaries (`app/services/chunking.py`),
  never mid-sentence unless a single sentence exceeds the model limit.
* Chunks are generated sequentially with continuity hints (`previous_text` / `next_text` for
  ElevenLabs), then concatenated with 220 ms gaps and loudness normalisation (`-16 LUFS`) via
  FFmpeg, and validated with ffprobe before the video stage sees them.
* Per-chunk metadata (characters, bytes, duration, latency, text preview) is stored in
  `tts_generations.chunk_manifest`.
* Audio is stored through the existing storage backend and served via the authenticated
  `/api/v1/files/{key}` route (proxied by the web app).

### Production integration

The Voice Agent receives the resolved configuration in its context (`tts_config`,
`tts_credential_version`) and records `provider`, `model_id`, `voice_id`, `voice_settings`,
`output_format` and duration on every `audio_assets` row. The content detail API exposes them as
`audio_provider`, `audio_model`, `audio_voice_id`.

---

## 5. Audio Studio

`/studio/audio` — three modes:

1. **Single voice** — provider, model, voice (with provider preview), language, provider-specific
   settings (only the ones the selected model supports), output format, generate, download.
2. **A/B compare** — one script, two provider/voice configurations, generated concurrently; the
   verdict reports which side is cheaper and faster (it never claims a subjective quality winner).
3. **Dialogue** — multi-speaker script for providers with a dialogue endpoint.

Every generation is a *test* generation: `trigger=studio`, `is_test=true`, never published, and
labelled "TEST" in history. Requests can be cancelled while in flight; the input and settings are
preserved. Errors are shown with the provider's own message.

> Long-running work note: generation is synchronous HTTP (a single narration chunk is seconds).
> Batch/`compare` requests run both sides concurrently. For very long texts the UI splits by the
> model limit and the server chunks internally, so a single click stays well below typical proxy
> timeouts.

---

## 6. Usage and cost

`tts_generations` (one row per request, success or failure) and `tts_usage_logs` (append-only,
characters as the unit) feed `GET /api/v1/tts/usage`:

* totals: generations, succeeded, failed, characters, audio seconds, estimated and actual cost,
  average latency;
* by provider, by model, by day.

Cost estimates use configured contract rates (`ai_providers.models[].unit_cost`) first, otherwise
published list prices (`app/services/pricing.py`). Estimated and actual (provider-reported) costs
are kept in separate columns and never mixed.

---

## 7. Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENCRYPTION_KEY` | — | **Required.** 32-byte AES-256-GCM master key. |
| `CREDENTIAL_KEY` | — | Legacy alias, read only when the above is empty. |
| `VOICE_MAX_CHARS` | `12000` | Chunk size when the provider publishes no limit. |
| `TTS_CONNECT_TIMEOUT_S` | `10` | Connection timeout for provider calls. |
| `TTS_REQUEST_TIMEOUT_S` | `120` | Read timeout for provider calls. |
| `TTS_MAX_ATTEMPTS` | `3` | HTTP retries inside an adapter. |
| `CARTESIA_API_KEY` / `ELEVENLABS_API_KEY` | — | Optional; DB credentials take precedence. |

---

## 8. Testing both providers

**Without keys (CI / local):**

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m pytest tests -q
```

The suite covers encryption, masking, rotation, RBAC, audit, empty-value protection, both adapters
(connection, models, voices, generation, dialogue, 401, 429, timeout, text limits, redaction),
chunking, inheritance, fallback, persistence, usage and the Studio endpoints — all against a fake
HTTP transport, so no key and no network are needed.

**With keys:**

1. Providers → Cartesia/ElevenLabs → add key → **test connection** (should list models and voices).
2. Audio Studio → pick provider/model/voice → generate → listen and download.
3. A/B compare the same line across Cartesia and ElevenLabs.
4. Start a production run from a channel; the workflow log shows
   `Narration generated · … characters · cartesia`.

---

## 9. Remaining limitations

* The web UI edits workspace and provider defaults; channel overrides are available through the API
  (`PUT /api/v1/tts/channels/{id}`).
* Generation is synchronous. Very long narrations are chunked server-side, but there is no
  background job queue for a single Studio request yet.
* Actual billed cost is only recorded where a provider reports it; otherwise the ledger holds
  estimates.
* Cartesia voice cloning and ElevenLabs /v3 audio tags are not exposed in the UI.
