# FACTORY / Autonomous AI YouTube Content Factory

An operational studio for running one or many YouTube channels through a ten-agent content
pipeline — plan → script → storyboard → voice → visuals → render → quality control → SEO →
**human approval** → publish → analytics.

![Overview dashboard](apps/.shots/overview.png)

The interface is an **editorial control room**: white paper, near-black ink, hairline rules,
Instrument Serif display type, IBM Plex Mono metadata and a single functional lime accent.
Every number on screen is derived from stored rows; when an integration is missing the UI says so
and links to the exact setup instead of showing fake data.

## What is implemented

| Area | State |
|---|---|
| Multi-tenant auth, RBAC, audit, encrypted credentials | ✅ |
| Centralised AES-256-GCM credential vault (all providers, rotatable without restart, audited) | ✅ |
| 34-table PostgreSQL schema + Alembic migrations (verified on PG16 & SQLite) | ✅ |
| 10 agents with typed contracts, schema-validated outputs, repair round, cost rows | ✅ |
| LLM: OpenAI, Gemini, **OpenAI-compatible**, **Anthropic-compatible** (own endpoint + model discovery), mock | ✅ |
| Cartesia + ElevenLabs TTS with the unified `TTSProvider` interface (models, voices, dialogue, previews) | ✅ |
| Voice configuration inheritance: scene → workflow → channel → workspace, with optional fallback | ✅ |
| Long-form narration: sentence-aware chunking, per-chunk retry, FFmpeg assembly | ✅ |
| LLM structured output (JSON schema / responseSchema) | ✅ |
| Per-scene TTS + visuals, content-addressed storage (local / R2) | ✅ |
| Remotion video engine: compositions, transitions, captions, music, renderMedia() | ✅ renders MP4 |
| Remotion motion templates (editorial, children's, educational, storytelling, shorts) | ✅ 6 templates |
| Durable pipeline with retries, budget guard, cancellation, approval gate | ✅ |
| Temporal backend + local durable runner (auto-degrade) | ✅ verified against a live Temporal server |
| Scheduler: per-channel timezone, dedupe, concurrency | ✅ |
| QC: weighted checks, age-safety review, regenerate targets | ✅ |
| YouTube OAuth, upload, Made-for-Kids, analytics sync | ✅ code (needs Google client) |
| Web app: 13 pages incl. Audio Studio, command palette, shortcuts, responsive | ✅ |
| Tests: 63 API/agent/service tests (SQLite + PostgreSQL) | ✅ |

## Quick start

```bash
# 1. infrastructure (optional for the API — SQLite works with zero setup)
docker compose up -d postgres redis

# 2. Remotion video engine (Node 18+; required for rendering)
cd services/media-engine/remotion
npm install

# 3. API
cd ../../../apps/api
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev,temporal]"
cp ../../.env.example .env          # then: python -m app.cli gen-key  → APP_ENCRYPTION_KEY
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000   # renders in-process

# 4. Web
cd ../web
npm install
echo "API_INTERNAL_URL=http://127.0.0.1:8000" > .env.local
npm run dev                          # http://localhost:3000
```

Add a Cartesia or ElevenLabs key in **Providers → Text to speech**, then try it in
**Studio → Audio Studio** (single voice, A/B compare, dialogue). See
[docs/09-credentials-and-tts.md](docs/09-credentials-and-tts.md).

Bring your own model endpoint: **Providers → Add provider → LLM → OpenAI-compatible**
(or *Anthropic-compatible*), paste the base URL ending in `/v1` and the key, then press
**list models** — the endpoint's own `/models` route fills the list. See
[docs/10-video-engine.md](docs/10-video-engine.md) for the rendering pipeline.

Sign in with `admin@factory.app` / `factory-admin-2026` (from `.env`), then change the password in
**Settings → Security**.

## Repository

```
apps/web            Next.js 16 · TypeScript · Tailwind v4 · Recharts · editorial shadcn-style primitives
apps/api            FastAPI · SQLAlchemy 2 · Alembic · JWT · AES-256-GCM vault
  app/agents        10 agents + contracts + structured-output runner + registry
  app/adapters      OpenAI · Gemini · OpenAI/Anthropic-compatible · Cartesia · ElevenLabs · R2 · Remotion · YouTube
  app/services      render queue (Remotion) · storyboard spec builder · TTS · credentials · pricing
  app/workflow      pipeline · scheduler · local durable runner · Temporal adapter
  app/api/v1        REST routers
  tests             80+ tests (auth, RBAC, agents, QC, storage, providers, TTS, render)
services/media-engine/remotion   Remotion compositions, templates, render CLI
infrastructure/docker            API/web images, nginx
docs                            architecture · design system · schema · agents · phases · api · deployment
```

## Design principles

1. **Providers are replaceable** — agents depend on ports, never vendor SDKs.
2. **AI output is untrusted** — every agent response is validated against a Pydantic contract; one
   repair round, then a hard failure.
3. **State is durable** — a run lives in the database; HTTP requests only start work.
4. **No fabricated operations** — setup states, empty states and mock labels are explicit.
5. **Humans gate publishing** — approval is required by default for Made-for-Kids content.

Docs: [docs/README.md](docs/README.md)
