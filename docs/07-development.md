# 07 · Development guide

## Prerequisites

- Node 22+, npm 10+
- Python 3.12 (`py -3.12` on Windows)
- Docker (Postgres/Redis; optional Temporal)
- FFmpeg + ffprobe on PATH (bundled in the API image)

## Run locally

```powershell
# infrastructure (optional — SQLite works with zero setup for the API)
docker compose up -d postgres redis

# API
cd apps/api
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,temporal]"
Copy-Item ..\..\.env.example .env
# set CREDENTIAL_KEY:
.\.venv\Scripts\python.exe -m app.cli gen-key      # paste into .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Web (new terminal)
cd apps/web
npm install
"API_INTERNAL_URL=http://127.0.0.1:8000" | Out-File .env.local
npm run dev
```

Open http://localhost:3000 and sign in with `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`
(default `admin@factory.app` / `factory-admin-2026` — change it in Settings → Security).

On first boot with SQLite the API creates the schema, seeds the workspace, the demo channel,
the agent registry and provider catalogue. With Postgres use `alembic upgrade head` first.

## Tests

```bash
cd apps/api
.\.venv\Scripts\python.exe -m pytest -q          # 23 tests, isolated SQLite db
# against PostgreSQL (production engine):
$env:DATABASE_URL="postgresql+asyncpg://factory:factory_dev_password@127.0.0.1:5432/factory"
.\.venv\Scripts\python.exe -m pytest -q
```

Smoke scripts (in `apps/api/scripts/`):

| script | purpose |
|---|---|
| `smoke_pipeline.py` | agents return schema-valid output with the mock provider |
| `smoke_render.py` | FFmpeg compositor produces an MP4 from mock assets |
| `smoke_http.py <api>` | login → production → approval gate through the HTTP API |
| `smoke_temporal.py <api>` | same, then inspects the Temporal activity history |
| `smoke_temporal_signal.py <id>` | workflow parked at the gate ends when signalled |

Web visual review (headless screenshots into `apps/.shots/`):

```bash
cd apps/web
node scripts/capture.mjs / /workflows /content /agents …
node scripts/capture-detail.mjs
```

## Adding an agent

1. Define input/output contracts in `app/agents/contracts.py` (Pydantic, `extra="forbid"`).
2. Implement the agent (subclass `LLMAgent` for prompt+schema agents, or write `run()` directly for
   port orchestration) in `app/agents/…`.
3. Register it in `app/agents/registry.py` with key, stage, port and description.
4. Call it from the pipeline (`app/workflow/pipeline.py`) in the right stage.
5. Restart the API — `bootstrap` refreshes the registry; the UI lists it automatically.

## Adding a provider

1. Implement the port (`LLMProvider`, `TTSProvider`, `ImageProvider`, …) in `app/adapters/`.
2. Add a builder branch in the same module and in `app/container.py` (`ProviderFactory.build`).
3. Add the slug to `SUPPORTED` in `app/api/v1/providers.py` and to `ADAPTERS` in the web
   providers page so administrators can select it.

No business logic changes: agents only see the port.

## Code style

- `ruff check app tests` (config in `pyproject.toml`), `mypy app` optional.
- TypeScript strict; `npx tsc --noEmit`, `npm run lint`.
- Layering: routers → services → ports/repositories. Adapters never import services.
