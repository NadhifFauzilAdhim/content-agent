"""Exposes which integrations are configured (never the secrets themselves)."""

from __future__ import annotations

from app.adapters.media import ffmpeg_available
from app.core.crypto import CredentialError, get_vault
from app.core.settings import get_settings


def app_config() -> dict:
    s = get_settings()
    try:
        get_vault()
        vault_ok = True
    except CredentialError:
        vault_ok = False
    # The video engine is Remotion. `ffmpeg_available` only reports whether ffprobe/ffmpeg binaries
    # exist on the host (used for inspection), never the composition engine.
    from app.services.render import engine_status

    engine = engine_status()
    return {
        "environment": s.environment,
        # Environment-only view. The dashboard client lives in the credential vault and is
        # reported by GET /providers/youtube/google/client (or /channels/youtube/status), which
        # has a database session.
        "google_oauth_configured": bool(s.google_client_id and s.google_client_secret),
        "storage_backend": s.storage_backend,
        "workflow_backend": s.workflow_backend,
        "ffmpeg_available": ffmpeg_available(),
        "video_engine": {
            "name": "remotion",
            "ok": engine["ok"],
            "version": engine.get("remotion"),
            "node": engine.get("node"),
            "detail": engine["detail"],
        },
        "credential_vault_ready": vault_ok,
        "scheduler_enabled": s.scheduler_enabled,
    }
