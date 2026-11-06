# Configuration ownership

| Concern | Lives in | Enforced by |
|---|---|---|
| Runtime environment (DB, Redis, JWT secret, vault key, storage, Temporal) | `.env` → `app/core/settings.py` | pydantic-settings, validated at boot |
| Non-secret integration flags for the UI | `app/core/config_view.py` → `GET /auth/config` | single source, never includes secrets |
| Provider credentials & model prices | `ai_providers` rows (Fernet-encrypted) | `app/core/crypto.py` |
| Agent bindings (provider, model, prompt, temperature) | `agent_configurations` rows | UI → `PUT /agents/{key}/config` |
| Channel policy (approval mode, quality floor, cost ceiling) | `channel_settings` rows | UI → channel page |
| Design tokens (colour, type, radii) | `apps/web/src/app/globals.css` `@theme` / `:root` | Tailwind v4 |
| Docker/service topology | `docker-compose.yml` + `infrastructure/docker/*` | compose profiles |

Secrets are never duplicated into the web app: the browser only sees the API through the Next.js
server, and provider keys never leave the API process.
