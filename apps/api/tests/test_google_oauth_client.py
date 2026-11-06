"""The Google OAuth client can be configured from the dashboard, not only from .env.

Covers the full lifecycle: unset → save (id + secret) → change id only (secret kept) → status
reports the dashboard as the source → remove → unset again.
"""

from __future__ import annotations

CLIENT_ID = "123456789012-abcdefghijklmnop.apps.googleusercontent.com"
OTHER_ID = "999999999999-zzzzzzzzzzzzzzzz.apps.googleusercontent.com"
SECRET = "GOCSPX-a-test-secret-value"


def test_google_client_lifecycle(client, auth):
    # Clean slate for this test run.
    client.delete("/api/v1/providers/youtube/google/client")

    before = client.get("/api/v1/providers/youtube/google/client").json()
    assert before["configured"] is False
    assert before["source"] is None
    assert before["redirect_uri"].endswith("/youtube/callback")

    saved = client.put(
        "/api/v1/providers/youtube/google/client",
        json={"client_id": CLIENT_ID, "client_secret": SECRET},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["configured"] is True
    assert body["source"] == "dashboard"
    assert body["has_secret"] is True
    # The secret is never returned; the id is masked.
    assert SECRET not in saved.text
    assert body["client_id_masked"].startswith("123456789012")
    assert body["secret_updated_at"] is not None

    # Changing only the id keeps the stored secret.
    kept = client.put(
        "/api/v1/providers/youtube/google/client", json={"client_id": OTHER_ID}
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["has_secret"] is True
    assert kept.json()["client_id_masked"].startswith("999999999999")

    # Channel status reports the dashboard client as the active source.
    status = client.get("/api/v1/youtube/status").json()
    assert status["oauth_configured"] is True
    assert status["oauth_source"] == "dashboard"

    # Removing it falls back to unset (no environment client in tests).
    assert client.delete("/api/v1/providers/youtube/google/client").status_code == 204
    after = client.get("/api/v1/providers/youtube/google/client").json()
    assert after["configured"] is False
    assert after["source"] is None


def test_google_client_rejects_a_non_google_id(client, auth):
    response = client.put(
        "/api/v1/providers/youtube/google/client",
        json={"client_id": "not-a-google-client-id", "client_secret": SECRET},
    )
    assert response.status_code == 422
    assert "apps.googleusercontent.com" in response.json()["error"]["message"]


def test_oauth_consent_url_uses_the_dashboard_client(client, auth):
    """The consent URL must carry the stored client id, not the (empty) environment one."""
    import asyncio

    from app.db.session import SessionFactory
    from app.services import youtube_oauth

    client.delete("/api/v1/providers/youtube/google/client")
    client.put(
        "/api/v1/providers/youtube/google/client",
        json={"client_id": CLIENT_ID, "client_secret": SECRET},
    )
    try:
        async def build() -> str:
            async with SessionFactory() as session:
                return await youtube_oauth.consent_url_for(session, "state-token")

        url = asyncio.run(build())
        assert CLIENT_ID in url
        assert "access_type=offline" in url
    finally:
        client.delete("/api/v1/providers/youtube/google/client")
