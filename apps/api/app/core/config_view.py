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
    return {
        "environment": s.environment,
        "google_oauth_configured": bool(s.google_client_id and s.google_client_secret),
        "storage_backend": s.storage_backend,
        "workflow_backend": s.workflow_backend,
        "ffmpeg_available": ffmpeg_available(),
        "credential_vault_ready": vault_ok,
        "scheduler_enabled": s.scheduler_enabled,
    }
