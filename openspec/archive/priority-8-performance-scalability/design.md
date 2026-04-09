# Design: Priority 8 — Performance & Scalability Optimization

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│              PRIORITY 8: ASYNC + MONITORING + CLEANUP               │
│                                                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │   Milestone 1: Async Task Execution                           │  │
│  │   ├─ asyncio.gather() for parallel I/O operations             │  │
│  │   ├─ async_utils.py shared primitives                         │  │
│  │   └─ Feature flag ROAMIN_USE_ASYNC (default off)              │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              ↓                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │   Milestone 2: Resource Monitoring & Throttling               │  │
│  │   ├─ resource_monitor.py (CPU/GPU/RAM checks)                 │  │
│  │   ├─ /health endpoint (Control API)                           │  │
│  │   └─ Throttle on threshold breach (max 3 retries)             │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              ↓                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │   Milestone 3: Background Task Cleanup                        │  │
│  │   ├─ SQLite cleanup (>24h retention window)                   │  │
│  │   ├─ schedule.every(5).minutes.do(_cleanup_completed_tasks)   │  │
│  │   └─ POST /actions/cleanup-tasks endpoint                     │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Milestone 1: Asynchronous Task Execution

### Current State (Blocking)

```python
# agent/core/agent_loop.py (current)
def _execute_step(self, step):
    # Blocking I/O operations freeze UI
    result = self._registry.execute(step["tool_name"], step.get("params", {}))
    return result
```

**Problem:** `web_search()`, `_file_read_async()` use blocking calls → UI freezes during execution.

### New Design (Async)

```python
# agent/core/async_utils.py (new)
import asyncio
from typing import Any, Callable


class AsyncRetryError(Exception):
    """Raised when async operation exceeds retry limit."""
    pass


async def async_retry(
    func: Callable[..., Any],
    *args,
    max_retries=2,
    delay=1.0,
    **kwargs
) -> Any:
    """
    Retry async function with exponential backoff.

    Usage:
        result = await async_retry(async_web_search, query="hello", max_retries=2)
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except (asyncio.TimeoutError, ConnectionError) as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(delay * (2 ** attempt))  # Exponential backoff

    raise AsyncRetryError(f"Operation failed after {max_retries + 1} attempts: {last_error}")


async def async_web_search(query: str, timeout: float = 30.0) -> list[dict]:
    """Async wrapper for ddgs search (non-blocking I/O)."""
    import asyncio
    from duckduckgo_search import DDGS

    loop = asyncio.get_event_loop()

    def _sync_search():
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=5))

    return await asyncio.wait_for(
        loop.run_in_executor(None, _sync_search),
        timeout=timeout
    )


# agent/core/agent_loop.py (refactored)
import asyncio


class AgentLoop:
    def __init__(self, registry, ...):
        self._registry = registry

    async def _execute_step_async(self, step: dict) -> dict:
        """Execute a single step asynchronously."""

        tool_name = step["tool_name"]
        params = step.get("params", {})

        # Check for resource exhaustion before execution
        if self._should_throttle():
            return {
                "success": False,
                "error": "Agent resources exhausted — try again later",
                "throttled": True
            }

        # Async tool execution
        if tool_name == "web_search":
            result = await async_retry(async_web_search, params.get("query", ""), max_retries=2)
            return {"success": True, "result": str(result)}

        # Fallback to registry.execute() for non-async tools (thread-safe)
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._registry.execute(tool_name, params)
            )
            return result

    async def run(self, plan: list[dict], ...) -> dict:
        """Run all steps in parallel using asyncio.gather()."""

        # Execute all steps in parallel
        tasks = [self._execute_step_async(step) for step in plan]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append({
                    "step": i,
                    "success": False,
                    "error": str(result)
                })
            else:
                final_results.append(result)

        return {"completed_steps": final_results}
```

### Key Design Decisions

1. **Async for I/O-heavy tools only** — web search, file reads (git CLI remains sync for simplicity)
2. **ThreadPoolExecutor fallback** — non-async tools use `loop.run_in_executor()` to avoid blocking
3. **Feature flag** — `ROAMIN_USE_ASYNC` (default off) enables gradual rollout

---

## Milestone 2: Resource Monitoring & Throttling

### New File: `agent/core/resource_monitor.py`

```python
"""
================================================================================
RESOURCE MONITOR — CPU/GPU/RAM THROTTLING LOGIC
Purpose: Monitor system resources and trigger throttling when exhausted.
================================================================================
"""

from __future__ import annotations
import psutil


def get_cpu_percent(interval: float = 0.5) -> float:
    """Return current CPU usage percentage."""
    return psutil.cpu_percent(interval=interval)


def get_ram_usage_mb() -> int:
    """Return current RAM usage in MB."""
    return int(psutil.virtual_memory().used / (1024 * 1024))


def get_vram_usage_mb() -> int | None:
    """
    Return VRAM usage in MB using nvidia-smi.

    Returns None if GPU not available or command fails.
    """
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass

    return None


def is_resource_exhausted(
    threshold_cpu: float = 90.0,
    threshold_ram_mb: int = 16000,  # 16GB default
    threshold_vram_mb: int | None = 20000  # 20GB default (RTX 3090)
) -> bool:
    """
    Check if system resources are exhausted.

    Args:
        threshold_cpu: CPU % threshold (default 90%)
        threshold_ram_mb: RAM MB threshold (default 16GB)
        threshold_vram_mb: VRAM MB threshold (default 20GB, or None to skip)

    Returns:
        True if any resource exceeds threshold
    """
    # Check CPU
    cpu = get_cpu_percent()
    if cpu > threshold_cpu:
        return True

    # Check RAM
    ram_mb = get_ram_usage_mb()
    if ram_mb > threshold_ram_mb:
        return True

    # Check VRAM (if available)
    if threshold_vram_mb is not None:
        vram_mb = get_vram_usage_mb()
        if vram_mb is not None and vram_mb > threshold_vram_mb:
            return True

    return False


def get_throttle_status() -> dict[str, float | bool]:
    """Return current resource status for /health endpoint."""

    cpu = get_cpu_percent(interval=0.5)
    ram_mb = get_ram_usage_mb()
    vram_mb = get_vram_usage_mb()
    exhausted = is_resource_exhausted()

    return {
        "cpu_percent": round(cpu, 2),
        "ram_mb": ram_mb,
        "vram_mb": vram_mb,
        "throttled": exhausted
    }
```

### Integration with AgentLoop

```python
# agent/core/agent_loop.py (updated)

class AgentLoop:

    def __init__(self, registry, ...):
        self._registry = registry

    async def _execute_step_async(self, step: dict) -> dict:
        """Execute a single step asynchronously."""

        # Check for resource exhaustion before execution
        if self._should_throttle():
            return {
                "success": False,
                "error": "Agent resources exhausted — try again later",
                "throttled": True
            }

        # ... rest of async execution logic

    def _should_throttle(self) -> bool:
        """Check if we should throttle this step."""
        from agent.core.resource_monitor import is_resource_exhausted

        return is_resource_exhausted()
```

---

## Milestone 3: Background Task Cleanup

### SQLite Cleanup Logic

```python
# agent/core/agent_loop.py (updated)

class AgentLoop:

    def _cleanup_completed_tasks(self, older_than_hours: int = 24) -> dict:
        """
        Delete completed tasks older than N hours.

        Args:
            older_than_hours: Retention window (default 24h)

        Returns:
            {deleted_count, oldest_retained_ts}
        """
        import sqlite3
        from datetime import datetime, timedelta

        db_path = Path(__file__).parent / "memory" / "roamin_memory.db"

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Calculate cutoff timestamp
        cutoff = (datetime.now() - timedelta(hours=older_than_hours)).isoformat()

        # Delete completed tasks older than cutoff
        cursor.execute("""
            DELETE FROM task_runs
            WHERE status = 'completed' AND started_at < ?
        """, (cutoff,))

        deleted_count = cursor.rowcount

        # Find oldest retained timestamp
        cursor.execute("""
            SELECT MIN(started_at) FROM task_runs
            WHERE status IN ('completed', 'running')
        """)
        result = cursor.fetchone()
        oldest_retained_ts = result[0] if result and result[0] else None

        conn.commit()
        conn.close()

        return {
            "deleted_count": deleted_count,
            "oldest_retained_ts": oldest_retained_ts
        }
```

### Scheduled Cleanup

```python
# run_wake_listener.py (updated)

import schedule


def _schedule_cleanup_tasks():
    """Schedule background cleanup every 5 minutes."""

    def job():
        from agent.core.agent_loop import AgentLoop

        loop = AgentLoop(...)
        result = loop._cleanup_completed_tasks(older_than_hours=24)

        # Log results
        print(f"[Cleanup] Deleted {result['deleted_count']} tasks, oldest retained: {result['oldest_retained_ts']}")

    schedule.every(5).minutes.do(job)
```

---

## Control API Endpoints

### New `/health` Endpoint

```python
# agent/control_api.py (updated)

@app.get("/health")
async def health_check():
    """Return current resource status."""
    from agent.core.resource_monitor import get_throttle_status

    return get_throttle_status()


@app.post("/actions/cleanup-tasks")
async def cleanup_tasks(older_than_hours: int = 24):
    """Trigger task cleanup manually."""
    from agent.core.agent_loop import AgentLoop

    loop = AgentLoop(...)
    result = loop._cleanup_completed_tasks(older_than_hours=older_than_hours)

    return result
```

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_async_utils.py
import pytest
import asyncio


@pytest.mark.asyncio
async def test_async_retry_success():
    """Test async_retry with successful operation."""
    async def success_func():
        return "ok"

    result = await async_retry(success_func, max_retries=2)
    assert result == "ok"


@pytest.mark.asyncio
async def test_async_retry_exhausted():
    """Test async_retry with repeated failures."""
    async def fail_func():
        raise ConnectionError("simulated failure")

    with pytest.raises(AsyncRetryError):
        await async_retry(fail_func, max_retries=1)


# tests/unit/test_resource_monitor.py
def test_cpu_percent_returns_valid_value():
    """Test CPU percent returns a number between 0-100."""
    cpu = get_cpu_percent()
    assert 0 <= cpu <= 100


def test_ram_usage_returns_positive_mb():
    """Test RAM usage returns positive value."""
    ram_mb = get_ram_usage_mb()
    assert ram_mb > 0
```

### Integration Tests

```python
# tests/integration/test_health_endpoint.py
import pytest


@pytest.mark.asyncio
async def test_health_endpoint_returns_resources():
    """Test /health endpoint returns CPU/RAM/VRAM."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get("http://127.0.0.1:8765/health")

        assert response.status_code == 200
        data = response.json()

        assert "cpu_percent" in data
        assert "ram_mb" in data
        assert "throttled" in data
```

---

## Failure Modes

| Failure | Impact | Mitigation |
|---|---|---|
| **asyncio.gather() fails** | Steps don't run in parallel | Fallback to sequential execution (existing logic) |
| **Resource monitor import fails** | No throttle checks | Graceful fallback (no throttling, but agent continues) |
| **SQLite cleanup fails** | Old tasks persist | Log warning, continue operation |

---

## Rollback Plan

If async refactor causes issues:

```bash
# Disable async execution via environment variable
set ROAMIN_USE_ASYNC=false
python launch.py
```

This reverts to existing ThreadPoolExecutor behavior.

---

## Acceptance Criteria

- [ ] `async_utils.py` and `resource_monitor.py` added to core module
- [ ] `/health` endpoint returns CPU/RAM/VRAM + throttle status
- [ ] Task cleanup runs every 5 min (scheduled)
- [ ] Test suite ≥250/261 passing

---

## Notes & Constraints

- PS5.1 ONLY — no `&&`, no `||`, no `?:` in PowerShell
- Python changes require `py_compile + flake8 --max-line-length=120`
- Use `Path(__file__).parent` for all paths (no hardcoded absolute paths)
- No debug print() in committed code
