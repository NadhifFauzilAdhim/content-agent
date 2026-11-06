# 05 · Phased implementation plan

Status legend: ✅ done in this repository run · 🟡 foundation in place, provider needs credentials · ⬜ next

## Phase 1 — Foundation ✅
- Monorepo scaffold, env schemas, Docker Compose (Postgres, Redis, API, web, workers).
- FastAPI app factory, settings, structured logging, error envelope, health/readiness.
- SQLAlchemy 2 models for all 27 entities + Alembic initial migration.
- JWT auth, RBAC, workspace tenancy, audit log, Fernet credential vault, rate limiting.
- Bootstrap CLI (admin, workspace, demo channel, agent registry, providers).
- Next.js 16 shell: sidebar, topbar, command palette, shortcut sheet, responsive drawer.
- Complete design system as Tailwind v4 tokens + primitives.
- Pages: Overview, Workflows (+detail), Agents, Content (+detail), Channels (+detail), Providers,
  Approvals, Costs, Analytics, Settings — every control wired to real endpoints or an explicit
  setup state.

## Phase 2 — AI infrastructure ✅ (adapters), 🟡 (live keys)
- Provider ports + real OpenAI/Gemini/TTS/Image adapters + mock adapters.
- Declarative agent registry, structured-output runner with repair round, usage/cost logging.
- Content Planner + Script Writer + Storyboard + SEO + QC agents; LangGraph-compatible graph.
- Providers page: add credential, test connection, health, fallback selection.

## Phase 3 — Content generation ✅ (mock path)
- Voice generation (Cartesia/ElevenLabs) per scene, real durations via audio probing.
- Visual generation, content-addressed storage (local/R2), media asset registry.
- Storyboard/scene regeneration endpoint.

## Phase 4 — Video engine ✅ (FFmpeg primary, Remotion template provided)
- FFmpeg compositor: scene images + narration + subtitles (ASS) + music mix, 16:9 / 9:16.
- Remotion project scaffold for advanced motion templates.
- Render jobs with progress, preview served through signed URLs.

## Phase 5 — Workflow automation ✅
- Temporal workflow (`ProductionWorkflow`) + stage activities + signal-based approval gate,
  verified end-to-end against a live Temporal server (`scripts/smoke_temporal.py`).
- In-process durable executor used automatically when Temporal is unavailable (jobs in Postgres, resumable).
- Scheduler with per-channel timezone, dedupe on partial unique index, concurrency limits.
- Retry/cancel/regenerate controls, timeline monitor, logs.

## Phase 6 — YouTube integration 🟡 (needs Google OAuth credentials)
- OAuth connect flow, encrypted token storage, resumable upload, Made-for-Kids, scheduling.
- Analytics collector, snapshots, dashboard, insights feeding back into planning.

## Phase 7 — Hardening ⬜/✅
- ✅ Rate limits, audit, validation, secrets at rest, health checks, graceful shutdown.
- ✅ Unit tests (agents/schemas/QC/rules) and integration tests (API with SQLite fallback).
- ⬜ Load testing, Sentry/OTel exporters, budget alerts, image CDN optimisation.
