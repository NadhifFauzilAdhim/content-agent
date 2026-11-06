"""OpenAI-compatible and Anthropic-compatible LLM providers, plus real provider deletion."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.adapters import llm as llm_mod
from app.ports.interfaces import Message, ProviderError


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, handler) -> None:  # type: ignore[no-untyped-def]
        self.handler = handler
        self.requests: list[dict] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = None
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = None
        self.requests.append({"url": str(request.url), "headers": dict(request.headers), "body": body})
        result = self.handler(request, body)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture()
def wire(monkeypatch):
    from app.adapters import http as http_mod

    state: dict = {}
    original = http_mod.httpx.AsyncClient

    def factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["transport"] = state["transport"]
        return original(*args, **kwargs)

    monkeypatch.setattr(http_mod.httpx, "AsyncClient", factory)

    def install(handler):  # type: ignore[no-untyped-def]
        transport = FakeTransport(handler)
        state["transport"] = transport
        return transport

    return install


# --------------------------------------------------------------------------- openai-compatible


def _openai_handler(request, body):
    path = request.url.path
    if path.endswith("/models"):
        return httpx.Response(200, json={"data": [
            {"id": "my-fast-model", "owned_by": "local"},
            {"id": "my-smart-model", "owned_by": "local", "context_length": 128000},
        ]})
    if body and body.get("response_format", {}).get("type") == "json_schema":
        return httpx.Response(400, json={"error": {"message": "response_format not supported"}})
    return httpx.Response(200, json={
        "model": body.get("model") if body else None,
        "choices": [{"message": {"content": "{\"ok\": true}"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
    })


def test_openai_compatible_lists_models_from_the_endpoint(wire):
    transport = wire(_openai_handler)
    provider = llm_mod.OpenAICompatibleProvider("sk-self", "https://llm.example.com/v1")
    models = asyncio.run(provider.list_models())
    assert [m["id"] for m in models] == ["my-fast-model", "my-smart-model"]
    assert transport.requests[0]["url"] == "https://llm.example.com/v1/models"
    assert transport.requests[0]["headers"]["authorization"] == "Bearer sk-self"


def test_openai_compatible_downgrades_json_mode_when_rejected(wire):
    transport = wire(_openai_handler)
    provider = llm_mod.OpenAICompatibleProvider("sk-self", "https://llm.example.com/v1")
    result = asyncio.run(provider.complete(
        model="my-fast-model",
        messages=[Message("user", "hi")],
        json_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    ))
    assert json.loads(result.content) == {"ok": True}
    assert result.usage.input_tokens == 11
    # first attempt used json_schema, second fell back to json_object
    modes = [r["body"].get("response_format", {}).get("type") for r in transport.requests]
    assert modes == ["json_schema", "json_object"]
    # the working mode is remembered, so the next call skips the rejected one
    asyncio.run(provider.complete(
        model="my-fast-model", messages=[Message("user", "again")],
        json_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    ))
    assert transport.requests[-1]["body"]["response_format"]["type"] == "json_object"
    assert provider._structured == "json_object"


def test_openai_compatible_does_not_mask_auth_errors(wire):
    wire(lambda request, body: httpx.Response(401, json={"error": {"message": "bad key"}}))
    provider = llm_mod.OpenAICompatibleProvider("bad", "https://llm.example.com/v1")
    with pytest.raises(ProviderError):
        asyncio.run(provider.complete(model="m", messages=[Message("user", "hi")],
                                      json_schema={"type": "object"}))


# --------------------------------------------------------------------------- anthropic-compatible


def _anthropic_handler(request, body):
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [
            {"id": "claude-self-1", "display_name": "Claude Self 1"},
        ]})
    return httpx.Response(200, json={
        "model": body.get("model"),
        "content": [{"type": "text", "text": "{\"ok\": true}"}],
        "usage": {"input_tokens": 21, "output_tokens": 7},
    })


def test_anthropic_compatible_uses_messages_api_conventions(wire):
    transport = wire(_anthropic_handler)
    provider = llm_mod.AnthropicCompatibleProvider("ak-self", "https://anthropic.example.com/v1")
    result = asyncio.run(provider.complete(
        model="claude-self-1",
        messages=[Message("system", "be brief"), Message("user", "hi")],
        max_tokens=256,
        json_schema={"type": "object"},
    ))
    request = transport.requests[-1]
    assert request["url"].endswith("/v1/messages")
    assert request["headers"]["x-api-key"] == "ak-self"
    assert request["headers"]["anthropic-version"]
    assert request["body"]["system"].startswith("be brief")
    assert request["body"]["max_tokens"] == 256
    assert [m["role"] for m in request["body"]["messages"]] == ["user"]
    assert json.loads(result.content) == {"ok": True}
    assert result.usage.output_tokens == 7


def test_anthropic_compatible_discovers_models(wire):
    wire(_anthropic_handler)
    provider = llm_mod.AnthropicCompatibleProvider("ak-self", "https://anthropic.example.com/v1")
    models = asyncio.run(provider.list_models(refresh=True))
    assert models[0]["id"] == "claude-self-1"
    assert models[0]["name"] == "Claude Self 1"


# --------------------------------------------------------------------------- provider deletion


def test_deleted_provider_is_gone_and_can_be_re_added(client, auth):
    """Deleting a provider must remove the secret itself, not just hide it."""
    created = client.post("/api/v1/providers", json={
        "kind": "llm", "slug": "anthropic-compatible", "name": "Temp gateway", "vendor": "Temp",
        "base_url": "https://anthropic.example.com/v1", "api_key": "ak-temp-key-abcdef123456",
        "models": [{"id": "claude-self-1"}],
    })
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    detail = client.get(f"/api/v1/providers/{pid}").json()
    assert detail["has_credential"] is True
    # The response never leaks the secret
    assert "ak-temp-key" not in created.text

    assert client.delete(f"/api/v1/providers/{pid}").status_code == 204
    assert client.get(f"/api/v1/providers/{pid}").status_code == 404
    # Re-adding the same adapter works because the unique row is gone (no "disable instead" state)
    again = client.post("/api/v1/providers", json={
        "kind": "llm", "slug": "anthropic-compatible", "name": "Temp gateway", "vendor": "Temp",
        "base_url": "https://anthropic.example.com/v1", "api_key": "ak-temp-key-abcdef123456",
    })
    assert again.status_code == 201, again.text
    client.delete(f"/api/v1/providers/{again.json()['id']}")


def test_provider_can_be_deleted_even_with_history(client, auth):
    created = client.post("/api/v1/providers", json={
        "kind": "llm", "slug": "openai-compatible", "name": "My gateway",
        "vendor": "Self-hosted", "base_url": "https://llm.example.com/v1",
        "api_key": "sk-own-key-1234567890", "models": [{"id": "my-model"}],
    })
    assert created.status_code == 201, created.text
    provider_id = created.json()["id"]
    assert created.json()["has_credential"] is True

    # bind it to an agent so the delete path has to clean up a reference
    bound = client.put("/api/v1/agents/content_planner/config", json={
        "provider_id": provider_id, "model": "my-model",
    })
    assert bound.status_code in (200, 201), bound.text

    deleted = client.delete(f"/api/v1/providers/{provider_id}")
    assert deleted.status_code == 204, deleted.text
    listing = client.get("/api/v1/providers").json()
    assert all(p["id"] != provider_id for p in listing)

    agent = next(a for a in client.get("/api/v1/agents").json() if a["key"] == "content_planner")
    assert agent["provider_id"] is None

    audit = client.get("/api/v1/workspace/audit", params={"limit": 20}).json()
    assert any(row["action"] == "provider.deleted" for row in audit)


def test_llm_provider_reads_its_stored_credential(wire):
    """A stored key must be readable through the same scope it was sealed with.

    Regression: the LLM/image path decrypted with the vault's bare ``decrypt()`` (AAD "default")
    while credentials are sealed with AAD ``provider:<workspace>:<provider>``, so every connection
    test failed with "The stored credential could not be authenticated" even though the key was
    correct.
    """
    from types import SimpleNamespace

    from app.adapters import http as http_mod
    from app.container import ProviderFactory
    from app.core.crypto import get_vault
    from app.services.credentials import aad_for

    provider = SimpleNamespace(
        id="pid-1",
        workspace_id="ws-1",
        kind="llm",
        slug="openai-compatible",
        name="Self",
        base_url="https://llm.example.com/v1",
        models=[{"id": "m"}],
        is_mock=False,
        extra_config={},
        credential_version=1,
    )
    provider.credential_ciphertext = get_vault().seal(
        {"api_key": "sk-from-vault-123456"}, aad=aad_for(provider)
    )
    # Silence the credential cache so this is a pure decrypt test.
    from app.services import credentials as creds

    creds._CACHE.clear()

    class _Session:
        async def flush(self):
            return None

    wire(lambda request, body: http_mod.httpx.Response(200, json={"data": []}))
    factory = ProviderFactory(_Session())
    import asyncio

    assert asyncio.run(factory._secret(provider)) == "sk-from-vault-123456"


def test_compatible_provider_requires_a_base_url(client, auth):
    resp = client.post("/api/v1/providers", json={
        "kind": "llm", "slug": "openai-compatible", "name": "No URL", "vendor": "Self",
        "api_key": "sk-whatever-123456",
    })
    assert resp.status_code == 422, resp.text
    assert "base URL" in resp.json()["error"]["message"]
