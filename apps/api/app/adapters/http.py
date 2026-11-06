"""HTTP helpers shared by adapters: timeout, exponential backoff, 429 handling."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from app.ports.interfaces import ProviderError, RateLimitedError

T = TypeVar("T")


async def with_retries(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
) -> T:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except RateLimitedError as exc:
            last = exc
            delay = exc.retry_after_s if exc.retry_after_s is not None else base_delay * 2 ** attempt
            delay = min(delay, max_delay) + random.uniform(0, 0.4)
        except (httpx.TimeoutException, httpx.TransportError, ProviderError) as exc:
            last = exc
            delay = min(base_delay * 2 ** (attempt - 1), max_delay) + random.uniform(0, 0.4)
        if attempt == attempts:
            break
        await asyncio.sleep(delay)
    raise last if last else ProviderError("unknown provider failure")


def raise_for_status(response: httpx.Response, provider: str) -> None:
    if response.status_code < 400:
        return
    retry_after = None
    try:
        retry_after = float(response.headers.get("retry-after", ""))
    except ValueError:
        pass
    body = response.text[:400]
    if response.status_code == 429:
        raise RateLimitedError(f"{provider} rate limited: {body}", status=429, retry_after_s=retry_after)
    raise ProviderError(f"{provider} error {response.status_code}: {body}", status=response.status_code)


def default_client(timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=10.0))
