"""Unit tests for agent.core.async_utils."""

from __future__ import annotations

import asyncio

import pytest

from agent.core.async_utils import AsyncRetryError, async_retry


@pytest.mark.asyncio
async def test_async_retry_success():
    """async_retry returns the result of a successful coroutine on the first attempt."""

    async def success():
        return "ok"

    result = await async_retry(success, max_retries=2)
    assert result == "ok"


@pytest.mark.asyncio
async def test_async_retry_succeeds_on_second_attempt():
    """async_retry retries after a transient ConnectionError."""
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("transient")
        return "recovered"

    result = await async_retry(flaky, max_retries=2, delay=0.01)
    assert result == "recovered"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_async_retry_exhausted():
    """async_retry raises AsyncRetryError when all attempts fail."""

    async def always_fail():
        raise ConnectionError("permanent failure")

    with pytest.raises(AsyncRetryError):
        await async_retry(always_fail, max_retries=1, delay=0.01)


@pytest.mark.asyncio
async def test_async_retry_timeout_error():
    """async_retry retries on asyncio.TimeoutError."""
    calls = {"n": 0}

    async def timeout_then_ok():
        calls["n"] += 1
        if calls["n"] == 1:
            raise asyncio.TimeoutError
        return "done"

    result = await async_retry(timeout_then_ok, max_retries=2, delay=0.01)
    assert result == "done"
