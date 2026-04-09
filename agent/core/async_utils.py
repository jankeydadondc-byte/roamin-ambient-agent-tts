"""Async utilities — retry, timeout, and non-blocking I/O helpers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class AsyncRetryError(Exception):
    """Raised when an async operation exceeds its retry limit."""


async def async_retry(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 2,
    delay: float = 1.0,
    **kwargs: Any,
) -> Any:
    """Retry an async callable with exponential backoff.

    Args:
        func: Async callable to invoke.
        *args: Positional arguments forwarded to func.
        max_retries: Number of additional attempts after the first (default 2).
        delay: Base delay in seconds; doubles on each retry (default 1.0).
        **kwargs: Keyword arguments forwarded to func.

    Raises:
        AsyncRetryError: When all attempts are exhausted.
    """
    last_error: BaseException | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except (asyncio.TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < max_retries:
                wait = delay * (2**attempt)
                logger.debug("async_retry: attempt %d failed (%s), retrying in %.1fs", attempt + 1, exc, wait)
                await asyncio.sleep(wait)

    raise AsyncRetryError(f"Operation failed after {max_retries + 1} attempt(s): {last_error}")


async def async_web_search(query: str, timeout: float = 30.0) -> list[dict]:
    """Non-blocking DuckDuckGo text search via thread-pool executor.

    Args:
        query: Search query string.
        timeout: Maximum seconds to wait (default 30).

    Returns:
        List of result dicts (keys: title, href, body).
    """
    loop = asyncio.get_event_loop()

    def _sync_search() -> list[dict]:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=5))

    return await asyncio.wait_for(
        loop.run_in_executor(None, _sync_search),
        timeout=timeout,
    )
