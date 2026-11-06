# 01 · System architecture

## Principles

1. **Business logic never depends on a provider.** Everything that talks to a third party goes
   through a port (Protocol) with at least one *real* adapter and one *in-process* adapter used for
   development. Agents only ever see the port.
2. **Structured outputs are contracts.** Every agent returns a Pydantic model; the LLM is instructed
   with the model's JSON schema and the raw output is validated, retried with the validation error
   fed back, and finally rejected.
3. **State is persistent and durable.** A workflow is a database row with stage, inputs, outputs,
   cost, retry count and timestamps. Long work runs in workers (Temporal), never inside an HTTP
   request.
4. **No fake operational data.** A dashboard metric is derived from stored rows. When an integration
   is not configured, the UI renders an explicit setup state, never fabricated numbers.

## Component map

```
                      ┌───────────────────────────────────────────────┐
  Browser ──HTTPS──▶  │ apps/web (Next.js 16, RSC + client islands)   │
                      │  · httpOnly session cookie (JWT)              │
                      │  · server actions / route handlers → API      │
                      └───────────────┬───────────────────────────────┘
                                      │ REST /api/v1 (JSON)
                      ┌───────────────▼───────────────────────────────┐
                      │ apps/api (FastAPI)                            │
                      │  routers → services → repositories → models   │
                      │  auth (JWT, RBAC, audit)                      │
                      │  crypto (Fernet envelope for credentials)     │
                      └───────┬───────────────┬───────────────────────┘
                              │               │ enqueue (Temporal client) / jobs table
        ┌─────────────────────▼──┐   ┌────────▼────────────────────────────┐
        │ services/ai-engine     │   │ services/workflow-engine             │
        │ provider ports+adapters│   │ Temporal workflows & activities      │
        │ agent registry         │   │ scheduler (cron per channel)          │
        │ LangGraph pipeline     │   │ retries, idempotency, concurrency     │
        └──────┬─────────────────┘   └────────┬─────────────────────────────┘
               │                              │
   ┌───────────▼──────────┐        ┌──────────▼─────────────┐
   │ LLM/TTS/IMG providers│        │ services/media-engine  │
   │ OpenAI Gemini Cartesia│       │ FFmpeg · Remotion ·    │
   │ ElevenLabs Replicate  │       │ Whisper · Pillow       │
   │ (mock adapters)       │       └──────────┬─────────────┘
   └──────────────────────┘                  │
                      ┌──────────────────────▼─────────────┐
                      │ PostgreSQL 16 · Redis 7 · R2/S3    │
                      └────────────────────────────────────┘
```

## Backend layout (`apps/api`)

```
app/
  main.py                 app factory, middleware, routers, lifespan
  core/                   settings, security (JWT/hash), crypto, errors, logging
  db/                     engine, session, base
  models/                 SQLAlchemy 2 declarative models (one module per domain)
  schemas/                Pydantic request/response models
  api/v1/                 routers (thin): auth, overview, channels, content, workflows,
                          agents, providers, costs, analytics, approvals, schedules, system
  services/               use-cases; pure business rules, depend on ports
  repositories/           query helpers
  ports/                  Protocols for LLM, TTS, Image, VideoRenderer, Storage, YouTube, Clock
  adapters/               concrete implementations of ports (real + mock)
  workers/                arq-compatible task entrypoints (render, publish, analytics)
  alembic/                migrations
  tests/
```

Dependency injection is a single `Container` built at startup (`app/container.py`) so routers can
resolve services through `Depends` and tests can swap adapters.

## Layering rules

| Layer | May import | Must not import |
|-------|-----------|-----------------|
| `api/v1` | services, schemas | models directly |
| services | ports, repositories, models, schemas | adapters, FastAPI |
| adapters | ports, third-party SDKs, httpx | services, routers |
| models | db, core | anything else |

This keeps provider swapping a configuration change (`ai_providers.kind`) rather than a code change.

## Frontend layout (`apps/web`)

```
src/
  app/
    (auth)/login/            split editorial login
    (app)/                   authenticated shell: sidebar + topbar + command palette
      page.tsx               Overview
      content/…              list + detail (script, storyboard, assets, QC, metadata)
      workflows/…            monitor + detail timeline
      agents/                registry + configuration
      channels/              list + detail (wizard-ish sections)
      providers/             provider registry + credentials + test connection
      costs/                 cost ledger and budgets
      analytics/             YouTube performance
      approvals/             approval queue (human-in-the-loop)
      settings/              workspace, team, security, API keys
  components/
    ui/                      shadcn-style primitives restyled to the design system
    shell/                   sidebar, topbar, command palette, page header
    domain/                  metrics, agent-traffic-map, pipeline, tables
  lib/api.ts                 typed server-side client for the FastAPI surface
  lib/auth.ts                cookie/session helpers
  styles/globals.css         design tokens
```

The web app never holds provider credentials. Provider rows expose `has_credential: bool` only.

## Auth & tenancy

- Email + password (Argon2/bcrypt), JWT (HS256) in an **httpOnly, sameSite=lax** cookie.
- Roles: `owner`, `admin`, `editor`, `viewer`, scoped per workspace (`workspace_members`).
- Every table that holds tenant data carries `workspace_id`; all queries are scoped by the caller's
  active workspace. Deny-by-default dependency `require_role(...)`.
- Audit log rows for auth events, credential changes, approvals and publishing.

## Reliability

- All agent activities idempotent by key `(workflow_id, task, attempt-scoped)`; providers get a
  client-side request id.
- Exponential backoff with jitter (`RetryPolicy` in Temporal, `tenacity` in-process for HTTP).
- Rate limit handling: 429 → honour `Retry-After`, then provider cooldown recorded in DB.
- Timeouts on every external call; hard per-stage timeouts in Temporal.
- Concurrency limits: per-channel semaphores and Temporal task queue max concurrency.
- Graceful shutdown: lifespan drains the Temporal worker and closes the engine pool.
- Health: `/healthz` (liveness), `/readyz` (DB + Redis + Temporal reachability).

## Not yet configured ≠ broken

`GET /api/v1/system/integrations` returns which ports have a configured credential. Pages render
`SetupState` components when a dependency is missing; they never render synthetic metrics.
