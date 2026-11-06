"""YouTube OAuth: consent URL, code exchange and access-token refresh (encrypted at rest)."""

from __future__ import annotations

import urllib.parse
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import get_vault
from app.core.errors import AppError, ProviderNotConfiguredError, ValidationAppError
from app.core.settings import get_settings
from app.models import Channel, YouTubeOAuthConnection

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def oauth_configured() -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret)


def consent_url(state: str) -> str:
    s = get_settings()
    if not oauth_configured():
        raise ProviderNotConfiguredError(
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )
    query = urllib.parse.urlencode(
        {
            "client_id": s.google_client_id,
            "redirect_uri": s.google_oauth_redirect,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )
    return f"{AUTH_URL}?{query}"


async def exchange_code(code: str) -> dict:
    s = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "redirect_uri": s.google_oauth_redirect,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise AppError(f"Google token exchange failed: {resp.text[:300]}")
    return resp.json()


async def refresh_access_token(session: AsyncSession, channel: Channel) -> str:
    conn = await session.scalar(
        select(YouTubeOAuthConnection).where(YouTubeOAuthConnection.channel_id == channel.id)
    )
    if conn is None:
        raise ProviderNotConfiguredError("This channel is not connected to YouTube")
    now = datetime.now(UTC)
    if conn.access_token and conn.access_expires_at and conn.access_expires_at > now + timedelta(minutes=2):
        return conn.access_token
    vault = get_vault()
    refresh_token = vault.decrypt(conn.refresh_ciphertext)
    s = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        conn.last_error = f"refresh failed: {resp.text[:200]}"
        await session.flush()
        raise ProviderNotConfiguredError(
            "YouTube authorization expired. Reconnect the channel under Channels → YouTube."
        )
    data = resp.json()
    conn.access_token = data["access_token"]
    conn.access_expires_at = now + timedelta(seconds=int(data.get("expires_in", 3600)))
    conn.last_refreshed_at = now
    conn.last_error = None
    conn.token_ciphertext = vault.encrypt(data["access_token"])
    await session.flush()
    return conn.access_token


async def store_connection(
    session: AsyncSession, channel: Channel, token_data: dict, channel_info: dict, scopes: list[str]
) -> YouTubeOAuthConnection:
    vault = get_vault()
    conn = await session.scalar(
        select(YouTubeOAuthConnection).where(YouTubeOAuthConnection.channel_id == channel.id)
    )
    if conn is None:
        refresh = token_data.get("refresh_token")
        if not refresh:
            raise ValidationAppError("Google did not return a refresh token. Revoke access and retry.")
        conn = YouTubeOAuthConnection(
            channel_id=channel.id,
            youtube_channel_id=channel_info["id"],
            refresh_ciphertext=vault.encrypt(refresh),
        )
        session.add(conn)
    conn.access_token = token_data.get("access_token")
    conn.access_expires_at = datetime.now(UTC) + timedelta(seconds=int(token_data.get("expires_in", 3600)))
    conn.scopes = scopes
    conn.channel_title = channel_info.get("title")
    channel.youtube_channel_id = channel_info["id"]
    channel.youtube_channel_title = channel_info.get("title")
    channel.youtube_connected_at = datetime.now(UTC)
    await session.flush()
    return conn
