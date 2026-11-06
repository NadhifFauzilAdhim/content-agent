"""Image adapters: OpenAI-compatible gateways with custom model ids and response shapes."""

from __future__ import annotations

import asyncio
import base64
import io
import json

import httpx
import pytest

from app.adapters import images as images_mod


def _png(width: int = 64, height: int = 36) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "#D6FF45").save(buffer, format="PNG")
    return buffer.getvalue()


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
            if isinstance(body, str):  # graphql-ish / form payloads are irrelevant here
                body = None
        self.requests.append({"url": str(request.url), "body": body})
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


# --------------------------------------------------------------------------- request shape


def test_custom_model_and_gateway_knobs_are_sent(wire):
    """Mirrors the gateway contract: model id, auto size, quality/background/detail/format."""
    png = _png(1024, 576)
    transport = wire(lambda request, body: httpx.Response(
        200, json={"data": [{"b64_json": base64.b64encode(png).decode()}]}
    ))
    adapter = images_mod.OpenAIImage(
        "sk-gateway",
        "https://gateway.example.com/v1",
        options={
            "size": "auto",
            "quality": "auto",
            "background": "auto",
            "image_detail": "high",
            "output_format": "png",
        },
        label="9router",
    )
    result = asyncio.run(adapter.generate(
        prompt="A cute cat wearing a hat", model="ag/gemini-3.1-flash-image", aspect_ratio="16:9"
    ))

    request = transport.requests[-1]
    assert request["url"] == "https://gateway.example.com/v1/images/generations"
    body = request["body"]
    assert body["model"] == "ag/gemini-3.1-flash-image"
    assert body["prompt"] == "A cute cat wearing a hat"
    assert body["n"] == 1
    assert body["size"] == "auto"
    assert body["quality"] == "auto"
    assert body["background"] == "auto"
    assert body["image_detail"] == "high"
    assert body["output_format"] == "png"
    # Dimensions come from the returned image, not the requested size.
    assert (result.width, result.height) == (1024, 576)
    assert result.usage.model == "ag/gemini-3.1-flash-image"
    assert result.data == png


def test_unset_knobs_are_omitted_for_strict_openai(wire):
    transport = wire(lambda request, body: httpx.Response(
        200, json={"data": [{"b64_json": base64.b64encode(_png(1792, 1024)).decode()}]}
    ))
    adapter = images_mod.OpenAIImage("sk-openai", "https://api.openai.com/v1")
    asyncio.run(adapter.generate(prompt="x", aspect_ratio="16:9"))
    body = transport.requests[-1]["body"]
    assert body["size"] == "1792x1024"  # a size the OpenAI API accepts
    for key in ("quality", "background", "image_detail", "output_format"):
        assert key not in body


def test_unknown_aspect_ratio_falls_back_to_auto(wire):
    transport = wire(lambda request, body: httpx.Response(
        200, json={"data": [{"b64_json": base64.b64encode(_png()).decode()}]}
    ))
    adapter = images_mod.OpenAIImage("sk", "https://gw.example.com/v1")
    asyncio.run(adapter.generate(prompt="x", aspect_ratio="21:9"))
    assert transport.requests[-1]["body"]["size"] == "auto"


# --------------------------------------------------------------------------- response shapes


def test_url_response_is_downloaded(wire):
    png = _png(512, 512)

    def handler(request, body):
        if request.url.path.endswith("/generations"):
            return httpx.Response(200, json={"data": [{"url": "https://cdn.example.com/a.png"}]})
        return httpx.Response(200, content=png, headers={"content-type": "image/png"})

    transport = wire(handler)
    adapter = images_mod.OpenAIImage("sk", "https://gw.example.com/v1")
    result = asyncio.run(adapter.generate(prompt="x", aspect_ratio="1:1"))
    assert result.data == png
    assert result.mime == "image/png"
    assert any("cdn.example.com" in r["url"] for r in transport.requests)


def test_data_uri_is_accepted(wire):
    png = _png(64, 64)
    uri = "data:image/png;base64," + base64.b64encode(png).decode()
    wire(lambda request, body: httpx.Response(200, json={"data": [{"b64_json": uri}]}))
    adapter = images_mod.OpenAIImage("sk", "https://gw.example.com/v1")
    result = asyncio.run(adapter.generate(prompt="x"))
    assert result.data == png


def test_empty_response_is_an_error(wire):
    from app.ports.interfaces import ProviderError

    wire(lambda request, body: httpx.Response(200, json={"data": []}))
    adapter = images_mod.OpenAIImage("sk", "https://gw.example.com/v1")
    with pytest.raises(ProviderError):
        asyncio.run(adapter.generate(prompt="x"))


def test_health_reports_auth_failure_distinctly(wire):
    wire(lambda request, body: httpx.Response(401, json={"error": "bad key"}))
    ok, detail = asyncio.run(images_mod.OpenAIImage("sk", "https://gw.example.com/v1").health())
    assert ok is False and "Authentication" in detail


def test_health_tolerates_missing_model_list(wire):
    wire(lambda request, body: httpx.Response(404, json={}))
    ok, detail = asyncio.run(images_mod.OpenAIImage("sk", "https://gw.example.com/v1").health())
    assert ok is True and "unavailable" in detail


def test_builder_passes_options_and_label():
    adapter = images_mod.build_image_provider(
        "openai-compatible",
        "sk",
        "https://gw.example.com/v1",
        options={"size": "auto", "image_detail": "high"},
        label="My gateway",
    )
    assert adapter._label == "My gateway"
    assert adapter._size_for("16:9") == "auto"


# --------------------------------------------------------------------------- provider selection


def test_model_follows_the_provider_that_was_actually_chosen(client, auth):
    """Regression: a bound model id must not be sent to a different provider.

    With ``visual_generation`` bound to provider A (model "bound-model") and A disabled, selection
    falls through to provider B. The request must carry B's own model — otherwise a gateway
    receives another vendor's model id and answers 404.
    """
    import asyncio
    import uuid

    from sqlalchemy import select

    from app.container import ProviderFactory
    from app.db.session import SessionFactory
    from app.models import Agent, AgentConfiguration, Channel

    def create(slug: str, name: str, model: str, key: str) -> str:
        """Create (or recreate) an image provider; the session DB may hold leftovers."""
        for provider in client.get("/api/v1/providers").json():
            if provider["kind"] == "image" and provider["slug"] == slug:
                client.delete(f"/api/v1/providers/{provider['id']}")
        response = client.post("/api/v1/providers", json={
            "kind": "image", "slug": slug, "name": name, "vendor": name,
            "base_url": "https://gw.example.com/v1",
            "api_key": key, "models": [{"id": model}],
        })
        assert response.status_code == 201, response.text
        return response.json()["id"]

    gateway_id = create("openai-compatible", "Gateway", "gw/image-model", "sk-test-key-123456")
    bound_id = create("gemini", "Bound", "bound-model", "sk-test-key-654321")

    async def bind(provider_id: str) -> None:
        async with SessionFactory() as session:
            agent = await session.scalar(select(Agent).where(Agent.key == "visual_generation"))
            config = await session.scalar(
                select(AgentConfiguration).where(AgentConfiguration.agent_id == agent.id)
            )
            if config is None:
                config = AgentConfiguration(agent_id=agent.id)
                session.add(config)
            config.provider_id = uuid.UUID(provider_id)
            config.model = "bound-model"
            await session.commit()

    async def resolve() -> tuple[str, str]:
        async with SessionFactory() as session:
            channel = await session.scalar(select(Channel))
            ctx = await ProviderFactory(session).build_context(
                agent_key="visual_generation", workspace_id=channel.workspace_id, channel=channel
            )
            return type(ctx.require_image()).__name__, ctx.model

    try:
        asyncio.run(bind(bound_id))
        # While the bound provider is enabled, its id is honoured.
        assert asyncio.run(resolve())[1] == "bound-model"

        client.patch(f"/api/v1/providers/{bound_id}", json={"is_enabled": False})
        adapter, model = asyncio.run(resolve())
        assert adapter == "OpenAIImage"
        assert model == "gw/image-model", model
    finally:
        async def unbind() -> None:
            async with SessionFactory() as session:
                agent = await session.scalar(select(Agent).where(Agent.key == "visual_generation"))
                config = await session.scalar(
                    select(AgentConfiguration).where(AgentConfiguration.agent_id == agent.id)
                )
                if config is not None:
                    config.provider_id = None
                    config.model = None
                    await session.commit()

        asyncio.run(unbind())
        client.delete(f"/api/v1/providers/{gateway_id}")
        client.delete(f"/api/v1/providers/{bound_id}")
