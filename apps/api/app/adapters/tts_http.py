"""Retry policy, error classification and cancellation for provider HTTP calls.

Every adapter funnels requests through :func:`request_with_retry` so behaviour is uniform:
connect/read timeouts, connection resets, 5xx and 429 are retried with full-jitter exponential
backoff; 400/401/403/404/422 become non-retryable configuration errors. Error text is redacted
and truncated — credentials never reach logs, audit rows or API responses.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.adapters.http import default_client
from app.core.logging import get_logger
from app.core.settings import get_settings
from app.ports.tts import (
    TTSAuthError,
    TTSConfigError,
    TTSInvalidRequestError,
    TTSRateLimitedError,
    TTSTransientError,
)

log = get_logger("factory.tts.http")

_TOKEN = re.compile(
    r"(?i:(?:bearer\s+|(?:xi[-\s]*)?api[_-]?key[\"']?\s*[:=]\s*[\"']?)?"
    r"(?:sk_[A-Za-z0-9_\-]{4,}|xi-[A-Za-z0-9_\-]{8,}))"
)
_LABELED = re.compile(
    r"(?i:((?:xi[-\s]*)?api[_-]?key)[\"']?\s*[:=]\s*)[^\s\",}]+"
)
_LABELED_SPACE = re.compile(r"(?i:(xi[-\s]*api[-\s]*key)\s+)[^\s\",}]+")


def redact(text: str, secret: str | None = None) -> str:
    out = text
    if secret:
        out = out.replace(secret, "[redacted]")
    # Replace credential tokens while keeping labels such as "bearer " or "api_key:".
    out = _TOKEN.sub("[redacted]", out)
    out = _LABELED.sub(lambda m: m.group(1) + ": [redacted]", out)
    out = _LABELED_SPACE.sub(lambda m: m.group(1) + " [redacted]", out)
    out = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+", "bearer [redacted]", out)
    return out[:400]


def secret_tag(secret: str | None) -> str:
    """Non-reversible tag so audit rows can prove *which* key was used without exposing it."""
    if not secret:
        return "none"
    return hashlib.sha256(secret.encode()).hexdigest()[:8]


def _error_body(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except (ValueError, UnicodeDecodeError):
        return redact(response.text)
    if isinstance(payload, dict):
        for key in ("detail", "message", "error", "detail_message"):
            value = payload.get(key)
            if isinstance(value, str):
                return redact(value)
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, dict) and isinstance(first.get("msg"), str):
                    return redact(str(first["msg"]))
            if isinstance(value, dict):
                return redact(str(value.get("message") or value.get("type") or value))
    return redact(response.text)


def _retry_after(response: httpx.Response) -> float | None:
    for header in ("retry-after", "retry-after-ms", "x-ratelimit-reset"):
        raw = response.headers.get(header)
        if not raw:
            continue
        try:
            value = float(raw)
            return value / 1000 if header.endswith("-ms") else value
        except ValueError:
            continue
    return None


def _json(response: httpx.Response) -> Any:
    """Parse a response body as JSON; WAV/audio bodies are not JSON, so treat them as empty."""
    try:
        return response.json()
    except (ValueError, UnicodeDecodeError):
        return {}


def _json_payload(response: httpx.Response) -> Any:
    """Like :func:`_json`, for 2xx bodies where empty JSON is a valid answer."""
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type.lower():
        return {}
    return _json(response)


def classify(response: httpx.Response, provider: str) -> Exception | None:
    """Map a non-2xx response to a typed error, or ``None`` when it is a success."""
    status = response.status_code
    if status < 400:
        return None
    body = _error_body(response)
    prefix = f"{provider}: "
    if status == 429:
        return TTSRateLimitedError(
            prefix + (body or "rate limit reached"), retry_after_s=_retry_after(response)
        )
    if status >= 500:
        return TTSTransientError(prefix + (body or f"upstream error {status}"), detail={"status": status})
    if status in (401, 403):
        return TTSAuthError(
            prefix + (body or "the API key was rejected"), detail={"status": status}
        )
    if status == 404:
        return TTSInvalidRequestError(
            prefix + (body or "resource not found (check the voice or model id)"),
            detail={"status": status},
        )
    if status in (400, 413, 422):
        return TTSInvalidRequestError(prefix + (body or "request rejected"), detail={"status": status})
    if status == 408:
        return TTSTransientError(prefix + "request timeout", detail={"status": status})
    return TTSConfigError(prefix + (body or f"unexpected status {status}"), detail={"status": status})


def wrap_transport(exc: Exception, provider: str) -> Exception:
    if isinstance(exc, httpx.TimeoutException):
        return TTSTransientError(f"{provider}: request timed out")
    if isinstance(exc, httpx.TransportError):
        return TTSTransientError(f"{provider}: network error ({type(exc).__name__})")
    if isinstance(exc, asyncio.CancelledError):
        return exc
    return exc


async def request_with_retry(
    factory: Callable[[httpx.AsyncClient], Awaitable[httpx.Response]],
    *,
    provider: str,
    timeout_s: float | None = None,
    connect_timeout_s: float | None = None,
    attempts: int | None = None,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
) -> httpx.Response:
    settings = get_settings()
    timeout = timeout_s or settings.tts_request_timeout_s
    connect = connect_timeout_s or settings.tts_connect_timeout_s
    total = max(1, attempts or settings.tts_max_attempts)

    # A single client per logical request keeps the connection pool warm for multi-chunk calls.
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=connect),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
    ) as client:
        last: Exception | None = None
        for attempt in range(1, total + 1):
            try:
                response = await factory(client)
            except Exception as exc:  # noqa: BLE001
                last = wrap_transport(exc, provider)
                delay = min(base_delay * 2 ** (attempt - 1), max_delay) * (0.5 + random.random())
            else:
                error = classify(response, provider)
                if error is None:
                    return response
                last = error
                retry_after = getattr(error, "retry_after_s", None)
                delay = retry_after if retry_after is not None else min(
                    base_delay * 2 ** (attempt - 1), max_delay
                )
                delay *= 0.5 + random.random()
                log.warning(
                    "tts.request_failed provider=%s status=%s attempt=%s code=%s",
                    provider,
                    response.status_code,
                    attempt,
                    getattr(error, "code", "error"),
                )
            if attempt == total or not getattr(last, "transient", False):
                break
            await asyncio.sleep(delay)
        assert last is not None
        raise last


def client_timeout(timeout_s: float | None = None) -> httpx.AsyncClient:
    """Plain client for cheap metadata calls (models, voices)."""
    return default_client(timeout_s or 20.0)


__all__ = [
    "classify",
    "client_timeout",
    "redact",
    "request_with_retry",
    "secret_tag",
    "wrap_transport",
]
