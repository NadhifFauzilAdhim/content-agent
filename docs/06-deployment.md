# Production VPS deployment (Docker Compose)

Target: a single VPS (2 vCPU / 4 GB+ recommended) running Ubuntu 24.04 or Debian 12.

## 1. Server preparation

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git ffmpeg
sudo usermod -aG docker $USER && newgrp docker
```

FFmpeg on the host is optional — the API image bundles FFmpeg + fonts.

## 2. Project

```bash
git clone <your-repo> /opt/factory && cd /opt/factory
cp .env.example .env
```

Edit `.env`:

| Variable | Production value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | `postgresql+asyncpg://factory:<strong-pw>@postgres:5432/factory` |
| `JWT_SECRET` | `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `CREDENTIAL_KEY` | `docker compose run --rm api python -m app.cli gen-key` |
| `COOKIE_SECURE` | `true` (behind HTTPS) |
| `WEB_ORIGIN` | `https://factory.example.com` |
| `GOOGLE_OAUTH_REDIRECT` | `https://factory.example.com/api/v1/youtube/callback` || `STORAGE_BACKEND` | `r2` (+ the four `R2_*` values) |
| `WORKFLOW_BACKEND` | `temporal` (recommended) |
| `BOOTSTRAP_ADMIN_PASSWORD` | a strong value, then change it in Settings |

`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are **optional**: enter them once in
*Providers → YouTube → manage key* and they are stored encrypted in the credential vault. Values in
the environment are only used as a fallback, so an existing deployment built on `.env` keeps working
and a dashboard value overrides it without a restart.

## 3. Start

```bash
# core stack
docker compose --profile full up -d --build

# optional: Temporal cluster (durable workflow engine)
docker compose --profile temporal up -d
```

The API container runs `alembic upgrade head`, bootstraps the first workspace (only if empty), and
starts. The worker container runs `python -m app.worker`.

## 4. HTTPS + reverse proxy

Run nginx (or Caddy/Traefik) in front of the `web` container using
`infrastructure/docker/nginx.conf`. With Caddy it is three lines:

```
factory.example.com {
  reverse_proxy localhost:3000
}
```

Never expose the API port publicly; the web app proxies authenticated requests.

## 5. Backups

Nightly database dump and storage sync:

```bash
0 3 * * * docker exec factory-postgres pg_dump -U factory factory | gzip > /backups/factory-$(date +%F).sql.gz
```
With R2, assets are already durable; with local storage, sync the `factory-storage` volume.

## 6. Upgrade

```bash
git pull
docker compose --profile full up -d --build   # migrations run on boot
```

## 7. Operational checklist

- [ ] `curl https://factory.example.com/api/v1/healthz` returns `ok`
- [ ] Login works and the cookie is `Secure; HttpOnly; SameSite=Lax`
- [ ] A provider test succeeds for each configured capability
- [ ] One full production reaches `awaiting_approval` with a playable render
- [ ] Approval without a YouTube connection shows the explicit blocked state
- [ ] Monthly budget is set in Costs
- [ ] Backups verified by restoring into a scratch database
