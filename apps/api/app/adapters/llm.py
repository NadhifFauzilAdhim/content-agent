"""LLM adapters: OpenAI, Google Gemini and a deterministic mock.

The adapter is selected by the ``ai_providers.slug`` column. Both real adapters accept a JSON
schema so structured outputs are enforced by the provider where supported.
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.adapters.http import default_client, raise_for_status, with_retries
from app.ports.interfaces import LLMProvider, LLMResult, Message, ProviderError, Usage


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1") -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")

    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_schema: dict[str, Any] | None = None,
        timeout_s: float = 120.0,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "structured_output", "schema": json_schema, "strict": False},
            }

        async def call() -> LLMResult:
            started = time.perf_counter()
            async with default_client(timeout_s) as client:
                resp = await client.post(
                    f"{self._base}/chat/completions",
                    headers={"Authorization": f"Bearer {self._key}"},
                    json=payload,
                )
            raise_for_status(resp, self.name)
            data = resp.json()
            choice = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage") or {}
            return LLMResult(
                content=choice,
                usage=Usage(
                    provider=self.name,
                    model=model,
                    operation="llm_chat",
                    input_tokens=int(usage.get("prompt_tokens", 0)),
                    output_tokens=int(usage.get("completion_tokens", 0)),
                    units=int(usage.get("total_tokens", 0)),
                    unit_label="tokens",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                ),
                raw=data,
            )

        return await with_retries(call)

    async def health(self) -> tuple[bool, str]:
        try:
            async with default_client(15) as client:
                resp = await client.get(
                    f"{self._base}/models", headers={"Authorization": f"Bearer {self._key}"}
                )
            if resp.status_code == 200:
                count = len(resp.json().get("data", []))
                return True, f"Connected · {count} models visible"
            return False, f"HTTP {resp.status_code}"
        except Exception as exc:  # noqa: BLE001 - health check must not raise
            return False, f"{type(exc).__name__}: {exc}"


class GeminiProvider:
    name = "gemini"
    _base = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_schema: dict[str, Any] | None = None,
        timeout_s: float = 120.0,
    ) -> LLMResult:
        system_parts = [m.content for m in messages if m.role == "system"]
        contents = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in messages
            if m.role != "system"
        ]
        gen_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_schema:
            gen_config["responseMimeType"] = "application/json"
            gen_config["responseSchema"] = _sanitize_schema(json_schema)
        payload: dict[str, Any] = {"contents": contents, "generationConfig": gen_config}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

        async def call() -> LLMResult:
            started = time.perf_counter()
            async with default_client(timeout_s) as client:
                resp = await client.post(
                    f"{self._base}/models/{model}:generateContent",
                    headers={"x-goog-api-key": self._key},
                    json=payload,
                )
            raise_for_status(resp, self.name)
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise ProviderError("Gemini returned no candidates (possible safety block)")
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            meta = data.get("usageMetadata", {})
            return LLMResult(
                content=text,
                usage=Usage(
                    provider=self.name,
                    model=model,
                    input_tokens=int(meta.get("promptTokenCount", 0)),
                    output_tokens=int(meta.get("candidatesTokenCount", 0)),
                    units=int(meta.get("totalTokenCount", 0)),
                    unit_label="tokens",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                ),
                raw=data,
            )

        return await with_retries(call)

    async def health(self) -> tuple[bool, str]:
        try:
            async with default_client(15) as client:
                resp = await client.get(
                    f"{self._base}/models", headers={"x-goog-api-key": self._key}
                )
            if resp.status_code == 200:
                return True, "Connected"
            return False, f"HTTP {resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"


def _sanitize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Gemini's responseSchema is a subset of JSON Schema."""

    allowed = {"type", "format", "description", "nullable", "enum", "items", "properties", "required"}
    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items() if k in allowed}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    cleaned = walk(schema)
    # Gemini requires a type on every property; default objects without type to string.
    def ensure(node: Any) -> None:
        if isinstance(node, dict):
            if "properties" in node:
                node.setdefault("type", "object")
            if "type" in node and node["type"] == "object" and "properties" not in node:
                node.pop("type")
            for v in node.values():
                ensure(v)
        elif isinstance(node, list):
            for v in node:
                ensure(v)

    ensure(cleaned)
    return cleaned


class MockLLMProvider:
    """Deterministic structured-output provider for development and tests.

    It does not invent stories: it echoes a clearly marked ``mock`` payload that satisfies the
    requested schema shape where possible, so the pipeline can be exercised end to end before a
    real provider is configured. The UI labels every mock run as such.
    """

    name = "mock"

    def __init__(self, fixture: dict[str, Any] | None = None) -> None:
        self._fixture = fixture or {}

    async def complete(
        self,
        *,
        model: str = "mock-1",
        messages: list[Message],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_schema: dict[str, Any] | None = None,
        timeout_s: float = 5.0,
    ) -> LLMResult:
        prompt = "\n".join(m.content for m in messages)
        if json_schema:
            fixture = self._fixture.get(_schema_hint(json_schema)) or mock_payload(
                _schema_hint(json_schema), prompt
            )
            content = json.dumps(fixture, ensure_ascii=False)
        else:
            content = f"[mock] {prompt[:200]}"
        tokens = max(1, len(prompt) // 4)
        return LLMResult(
            content=content,
            usage=Usage(
                provider=self.name,
                model=model,
                input_tokens=tokens,
                output_tokens=max(1, len(content) // 4),
                units=tokens,
                unit_label="tokens",
                latency_ms=5,
            ),
            raw={"mock": True},
        )

    async def health(self) -> tuple[bool, str]:
        return True, "Mock provider · no external calls"


def _schema_hint(schema: dict[str, Any]) -> str:
    return schema.get("title") or "default"


# Placeholder fields for the mock are never presented as a real topic: titles are prefixed with
# "MOCK" and the UI labels mock-provider runs as such.
_MOCK_SCENE_TEXT = (
    "The little lantern glows softly on the path. Pip takes a slow, brave step forward.",
    "Mossy smiles and lifts the lantern higher so the way is clear and warm.",
    "Pip reaches the burrow door, safe and sleepy, with the lantern still glowing.",
    "The stars settle down and the meadow grows quiet for the night.",
)


def mock_payload(schema_title: str, prompt: str) -> dict[str, Any]:
    """Deterministic, schema-shaped placeholder content for development without API keys."""
    scenes = [
        {
            "index": i + 1,
            "title": f"Mock scene {i + 1}",
            "narration": _MOCK_SCENE_TEXT[i % len(_MOCK_SCENE_TEXT)],
            "dialogue": (
                [{"character": "Mossy", "line": "Follow the light, little one.", "emotion": "warm"}]
                if i == 1 else []
            ),
            "duration_s": 8,
            "visual_instruction": "Storybook illustration, soft light, gentle mood",
            "sfx": ["soft breeze"],
            "transition": "fade",
        }
        for i in range(4)
    ]
    if schema_title == "ContentBrief":
        return {
            "title": "MOCK · The Lantern Path",
            "topic": "finding a way home",
            "angle": "Neighbours leave lanterns out so a small fox can find the path.",
            "audience": "Children 3-7",
            "brief": "Placeholder brief generated by the mock provider. Replace the LLM provider with a "
                     "real one (OpenAI or Gemini) under Providers to generate original content.",
            "creative_direction": "Soft gouache storybook, warm amber lamps against dusk blue.",
            "category": "story",
            "estimated_duration_s": 180,
            "safety_notes": ["no peril", "gentle sounds only"],
            "rationale": "Mock data for pipeline validation only.",
        }
    if schema_title == "ScriptDraft":
        return {
            "title": "MOCK · The Lantern Path",
            "description": "Placeholder script produced by the mock provider.",
            "hook": "When the light grew low, a tiny fox looked for the way home.",
            "scenes": scenes,
            "moral": "Asking for help is a kind thing to do.",
            "target_age": "3-7",
        }
    if schema_title == "StoryboardDraft":
        return {
            "style_guide": "Warm gouache storybook, soft edges, paper texture.",
            "scenes": [
                {
                    "index": s["index"],
                    "camera": "wide shot" if s["index"] % 2 else "medium close-up",
                    "composition": "rule of thirds, strong path leading line",
                    "characters": ["Pip"],
                    "background": "dusk meadow with glowing lanterns",
                    "action": "Pip follows the lantern light along the path",
                    "image_prompt": (
                        "Storybook illustration, small orange fox cub with a red knitted scarf on a path "
                        "at dusk, glowing lanterns on posts, warm amber light, soft gouache, no text"
                    ),
                    "negative_prompt": "text, watermark, signature, extra limbs, horror, weapons",
                    "sfx": ["soft breeze"],
                    "duration_s": s["duration_s"],
                    "transition": "fade",
                }
                for s in scenes
            ],
        }
    if schema_title == "MetadataDraft":
        return {
            "title": "MOCK · The Lantern Path | Bedtime Story",
            "description": "Placeholder description generated by the mock provider. Configure a real "
                           "LLM provider to generate accurate metadata for your video.",
            "tags": ["bedtime story", "children story", "kids", "calm", "lantern", "mock"],
            "thumbnail_text": "Follow the light",
            "thumbnail_concept": "A fox holds a lantern on a dusk path.",
            "thumbnail_prompt": "Small fox with lantern on a winding path at dusk",
            "playlist": "Bedtime Stories",
            "made_for_kids": True,
            "category": "Education",
        }
    if schema_title == "ContentSafetyReview":
        return {
            "age_appropriate": True,
            "policy_flags": [],
            "tone_notes": "Gentle, calm, no conflict.",
            "summary": "Mock safety review: content appears age-appropriate.",
        }
    # generic object shaped from the schema is not available here without the schema itself
    return {}


class OpenAICompatibleProvider:
    """Any endpoint that speaks the OpenAI Chat Completions API.

    This covers OpenAI itself, Groq, Together, Fireworks, OpenRouter, DeepSeek, Mistral, xAI,
    LM Studio, Ollama (`/v1`), vLLM, LiteLLM and most gateways. Nothing is assumed beyond the
    documented core: models are discovered from ``GET {base}/models`` so the UI can list exactly
    what the operator's endpoint exposes.

    ``json_schema`` support is not universal on compatible endpoints, so a schema is requested in
    three steps, most capable first:
      1. ``response_format={"type":"json_schema", ...}`` (OpenAI, newer servers)
      2. ``response_format={"type":"json_object"}`` (wider support; the schema travels in the prompt)
      3. plain completion (the runner still validates and repairs the JSON)
    The mode that worked is remembered per provider instance to avoid paying for 400s on every call.
    """

    name = "openai-compatible"
    _fallback_modes = ("json_schema", "json_object", "none")

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        label: str = "OpenAI-compatible",
        models_cache: list[dict[str, Any]] | None = None,
        structured_mode: str | None = None,
    ) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._label = label
        self._models_cache = models_cache or []
        self._structured = structured_mode

    # -- discovery ---------------------------------------------------------
    async def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if self._models_cache and not refresh:
            return self._models_cache
        async with default_client(20) as client:
            resp = await client.get(f"{self._base}/models", headers=self._headers())
        if resp.status_code >= 400:
            return self._models_cache
        payload = resp.json()
        rows = payload.get("data") if isinstance(payload, dict) else payload
        models: list[dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            model_id = row.get("id") or row.get("name")
            if not model_id:
                continue
            models.append({
                "id": str(model_id),
                "name": row.get("name") or str(model_id),
                "owned_by": row.get("owned_by"),
                "context_length": row.get("context_length") or row.get("context_window"),
            })
        models.sort(key=lambda m: m["id"])
        self._models_cache = models
        return models

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "Accept": "application/json"}

    # -- completion --------------------------------------------------------
    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_schema: dict[str, Any] | None = None,
        timeout_s: float = 120.0,
    ) -> LLMResult:
        order = [self._structured] if self._structured else list(self._fallback_modes)
        last_error: ProviderError | None = None
        for mode in order:
            if mode is None:
                continue
            try:
                result = await self._complete_once(
                    model=model, messages=messages, temperature=temperature,
                    max_tokens=max_tokens, json_schema=json_schema if mode != "none" else None,
                    mode=mode or "none", timeout_s=timeout_s,
                )
                self._structured = mode
                return result
            except ProviderError as exc:
                # Only a rejected request (4xx about response_format) justifies downgrading.
                if json_schema is None or exc.status not in (400, 404, 422):
                    raise
                last_error = exc
                continue
        raise last_error or ProviderError(f"{self._label}: completion failed")

    async def _complete_once(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float,
        max_tokens: int,
        json_schema: dict[str, Any] | None,
        mode: str,
        timeout_s: float,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_schema and mode == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": json_schema,
                    "strict": False,
                },
            }
        elif json_schema and mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
            payload["messages"] = [
                *payload["messages"],
                {
                    "role": "system",
                    "content": "Respond with a single JSON object. No prose, no markdown fences.",
                },
            ]

        started = time.perf_counter()
        async with default_client(timeout_s) as client:
            resp = await client.post(
                f"{self._base}/chat/completions", headers=self._headers(), json=payload
            )
        raise_for_status(resp, self._label)
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"{self._label} returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):  # some gateways return content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        usage = data.get("usage") or {}
        return LLMResult(
            content=content or "",
            usage=Usage(
                provider=self.name,
                model=data.get("model") or model,
                operation="llm_chat",
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                units=int(usage.get("total_tokens", 0)),
                unit_label="tokens",
                latency_ms=int((time.perf_counter() - started) * 1000),
            ),
            raw=data,
        )

    async def health(self) -> tuple[bool, str]:
        try:
            models = await self.list_models(refresh=True)
            if models:
                return True, f"Connected · {len(models)} models"
            return False, "Endpoint reachable but returned no models"
        except Exception as exc:  # noqa: BLE001 - health checks must not raise
            return False, f"{type(exc).__name__}: {exc}"


class AnthropicCompatibleProvider:
    """Any endpoint that speaks the Anthropic Messages API.

    Covers Anthropic itself, AWS Bedrock behind the Messages-compatible proxy, LiteLLM, OpenRouter's
    Anthropic routes and self-hosted gateways that implement ``POST /v1/messages``.

    Anthropic differs from OpenAI in ways that matter and are handled explicitly:
      * auth header is ``x-api-key`` plus a required ``anthropic-version``;
      * the system prompt is a top-level ``system`` field, not a message;
      * ``max_tokens`` is required;
      * the response is a list of content blocks;
      * there is no ``/models`` endpoint on every gateway, so discovery degrades to the models the
        operator typed in the provider form.
    """

    name = "anthropic-compatible"
    API_VERSION = "2023-06-01"
    _fallback_modes = ("none",)

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        label: str = "Anthropic-compatible",
        models_cache: list[dict[str, Any]] | None = None,
    ) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._label = label
        self._models_cache = models_cache or []

    async def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        """Best effort: try ``GET {base}/models`` (newer Anthropic API), else the configured list."""
        if self._models_cache and not refresh:
            return self._models_cache
        try:
            async with default_client(20) as client:
                resp = await client.get(f"{self._base}/models", headers=self._headers())
            if resp.status_code == 200:
                payload = resp.json()
                rows = payload.get("data") if isinstance(payload, dict) else payload
                models = [
                    {"id": str(r["id"]), "name": r.get("display_name") or str(r["id"])}
                    for r in rows or []
                    if isinstance(r, dict) and r.get("id")
                ]
                if models:
                    self._models_cache = sorted(models, key=lambda m: m["id"])
        except Exception:  # noqa: BLE001 - discovery is optional
            pass
        return self._models_cache

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
            "Accept": "application/json",
        }

    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_schema: dict[str, Any] | None = None,
        timeout_s: float = 120.0,
    ) -> LLMResult:
        system_parts = [m.content for m in messages if m.role == "system"]
        turns = [
            {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
            for m in messages
            if m.role != "system"
        ]
        if json_schema:
            system_parts.append(
                "Respond with a single JSON object that validates against this JSON Schema. "
                "No prose, no markdown fences.\n" + json.dumps(json_schema, separators=(",", ":"))
            )
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": turns,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        started = time.perf_counter()
        async with default_client(timeout_s) as client:
            resp = await client.post(f"{self._base}/messages", headers=self._headers(), json=payload)
        raise_for_status(resp, self._label)
        data = resp.json()
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
        usage = data.get("usage") or {}
        return LLMResult(
            content=text,
            usage=Usage(
                provider=self.name,
                model=data.get("model") or model,
                operation="llm_chat",
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                units=int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)),
                unit_label="tokens",
                latency_ms=int((time.perf_counter() - started) * 1000),
            ),
            raw=data,
        )

    async def health(self) -> tuple[bool, str]:
        try:
            models = await self.list_models(refresh=True)
            if models:
                return True, f"Connected · {len(models)} models"
            return True, "Endpoint configured · no model list published (models from the provider form)"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"


def build_llm_provider(
    slug: str,
    api_key: str | None,
    base_url: str | None,
    *,
    label: str | None = None,
    models: list[dict[str, Any]] | None = None,
) -> LLMProvider:
    if slug == "mock":
        return MockLLMProvider()
    if not api_key:
        raise ProviderError(f"Provider '{slug}' has no credential configured")
    if slug == "openai":
        return OpenAIProvider(api_key, base_url or "https://api.openai.com/v1")
    if slug == "gemini":
        return GeminiProvider(api_key)
    if slug == "openai-compatible":
        if not base_url:
            raise ProviderError("An OpenAI-compatible provider needs a base URL")
        return OpenAICompatibleProvider(
            api_key, base_url, label=label or "OpenAI-compatible", models_cache=models
        )
    if slug == "anthropic-compatible":
        if not base_url:
            raise ProviderError("An Anthropic-compatible provider needs a base URL")
        return AnthropicCompatibleProvider(
            api_key, base_url, label=label or "Anthropic-compatible", models_cache=models
        )
    raise ProviderError(f"Unsupported LLM provider '{slug}'")
