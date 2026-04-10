# Priority 9: Testing & Debugging

**Status:** DRAFT
**Date:** 2026-04-09
**Scope:** Test coverage for uncovered core modules + structured JSON logging + throttled logger

---

## Background

As of 2026-04-09, the test suite collects 123 tests across 20+ files. However, several
core modules added in recent phases have no test coverage at all:

| Module | Tests? | Risk |
|--------|--------|------|
| `agent/core/context_builder.py` | ❌ None | High — planner visibility regressions go undetected |
| `agent/core/agent_loop.py` (cleanup, throttle) | ❌ None | Medium — cleanup runs every 5 min in prod |
| `agent/plugins/mempalace.py` | ❌ None | Medium — tool dispatch correctness |
| `agent/core/roamin_logging.py` (JSON path) | ❌ None | Low — structured log parsing |

Additionally, `roamin_logging.py` has no JSON formatter, no throttled logger, and no
request ID tracing — the three features listed in the Priority 9 spec.

Error-recovery testing (9.3) is substantially complete via `tests/unit/test_async_utils.py`
(4 tests covering retry, backoff, and fallthrough). Only gap is direct dispatch retry path
in `wake_listener.py`.

---

## What We Are NOT Changing

- The 123 currently-collected tests — no deletions, no scope changes
- `agent/core/roamin_logging.py` public API — additive only
- Any tool dispatch logic (Priority 8 fixes are stable)
- The 11 collection errors (pre-existing, unrelated to this phase)

---

## Milestone 9.1 — Unit Tests for Uncovered Core Modules

### 9.1.1 `tests/unit/test_context_builder.py` (new)

Tests for `ContextBuilder.build()` — the function that drives AgentLoop planning.

**What to test:**
- `build()` with no registry returns a non-empty string
- `build()` with a real `ToolRegistry` that has one registered tool → tool appears in output
- `build()` with explicit `registry=` override uses that registry (not the internal one)
- `build()` with `screen_observation` includes the observation in output
- `build()` with `max_memory_results=0` doesn't crash

**Key design constraint:** ContextBuilder talks to ChromaDB/memory_store at `build()` time.
Tests must mock `memory_store` or use `max_memory_results=0` to avoid filesystem deps.

### 9.1.2 `tests/unit/test_agent_loop_cleanup.py` (new)

Tests for `AgentLoop._cleanup_completed_tasks()` and `_should_throttle()`.

**What to test (cleanup):**
- Returns `{"deleted_count": 0, "oldest_retained_ts": None}` when no rows exist
- Deletes rows where `status='completed'` AND `started_at < cutoff`
- Leaves rows where `status='completed'` but `started_at >= cutoff` (recent, keep)
- Leaves rows where `status='running'` regardless of age
- Returns correct `deleted_count`

**What to test (throttle):**
- `_should_throttle()` returns False when `is_resource_exhausted()` raises (fail-open)
- `_should_throttle()` returns True/False per mocked `is_resource_exhausted()` return value

**Setup:** Use a temporary SQLite file (tmp_path fixture) and patch `AgentLoop.__init__`
to point `self._db_path` at it, bypassing the real database.

### 9.1.3 `tests/unit/test_mempalace_plugin.py` (new)

Tests for `agent/plugins/mempalace.py`.

**What to test:**
- `Plugin()` instantiates with zero args without error
- `Plugin.name == "mempalace_memory"`
- `_status()` returns `{"success": True, "result": ...}` on subprocess success
- `_status()` returns `{"success": False, "error": ...}` on subprocess exception
- `_search()` with empty query returns `{"success": False, "error": "query is required"}`
- `_search()` returns `{"success": False, "error": "mempalace package not installed"}` when `search_memories` raises `ImportError`
- `_search()` formats hits into readable bullet strings under `"result"` key
- `on_load()` with `_MODE="plugin"` registers both tools (`mempalace_status`, `mempalace_search`)
- `on_load()` with `_MODE="standalone"` does NOT register tools, but starts MCP subprocess
- `on_unload()` terminates `_mcp_proc` if set

---

## Milestone 9.2 — Structured Logging Enhancements to `roamin_logging.py`

### What to add (additive — no existing API breaks):

#### 9.2.1 JSON Formatter

```python
class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object.

    Fields: timestamp (ISO-8601), level, logger, message, [request_id], [extra]
    Designed for log aggregators and grep-friendly debugging.
    """
```

Fields always present: `timestamp`, `level`, `logger`, `message`
Fields included when set on the LogRecord: `request_id`, any extra kwargs passed to `logger.info(..., extra={"request_id": ...})`

#### 9.2.2 Throttled Logger

```python
class ThrottledLogger:
    """Rate-limit repeated log messages to avoid log spam.

    Identical messages within `cooldown_seconds` (default: 60) are suppressed.
    A suppression summary ("X similar messages suppressed") is emitted when a new
    distinct message arrives or on explicit flush().
    """
    def __init__(self, logger: logging.Logger, cooldown_seconds: float = 60.0) -> None: ...
    def info(self, msg: str, **kwargs) -> None: ...
    def warning(self, msg: str, **kwargs) -> None: ...
    def flush(self) -> None: ...
```

Keying strategy: exact message string (not format args) for simplicity.

#### 9.2.3 Request ID Context

```python
_request_id_var: contextvars.ContextVar[str | None] = ContextVar("request_id", default=None)

def set_request_id(request_id: str) -> None: ...
def get_request_id() -> str | None: ...
def bind_request_id(request_id: str):  # context manager
    """Set request_id for duration of `with` block; restore previous on exit."""
```

`JsonFormatter` reads `_request_id_var` automatically — no call-site changes needed.

#### 9.2.4 `get_json_logger(name)` factory

```python
def get_json_logger(name: str, log_file: Path | None = None) -> logging.Logger:
    """Return a logger that emits JSON lines via JsonFormatter."""
```

Convenience factory so callers don't need to assemble handlers manually.

### Files changed:
- `agent/core/roamin_logging.py` — add `JsonFormatter`, `ThrottledLogger`, `_request_id_var`, helpers, `get_json_logger`
- `tests/unit/test_roamin_logging.py` (new) — see 9.2 tests below

### 9.2 Tests (`tests/unit/test_roamin_logging.py`)

- `JsonFormatter` output is valid JSON with required fields
- `JsonFormatter` includes `request_id` when set via `set_request_id()`
- `JsonFormatter` omits `request_id` key when not set
- `ThrottledLogger.info()` emits first message immediately
- `ThrottledLogger.info()` suppresses identical message within cooldown
- `ThrottledLogger.info()` emits after cooldown expires (mock time)
- `ThrottledLogger.flush()` emits suppressed count summary
- `bind_request_id` context manager restores previous value on exit
- `get_json_logger()` returns a logger whose handlers use `JsonFormatter`

---

## Milestone 9.3 — Error Recovery Testing (Gap Fill)

`test_async_utils.py` already covers `async_retry` extensively. One gap remains:

### 9.3.1 `tests/unit/test_wake_listener_dispatch.py` (new)

The direct dispatch path in `wake_listener.py` has no unit tests. The mempalace routing
fix (Priority 8) changed several regex patterns and registry wiring — all untested.

**What to test (no live audio, no keyboard, no llama_cpp):**
- `_try_direct_dispatch()` with a mempalace search trigger calls `mempalace_search` tool
- `_try_direct_dispatch()` with a palace status trigger calls `mempalace_status` tool
- `_try_direct_dispatch()` with a web search phrase routes to `web_search`
- `_try_direct_dispatch()` with an unrecognized phrase returns `None` (falls through to AgentLoop)
- `_try_direct_dispatch()` uses `agent_loop.registry` (not a fresh `ToolRegistry`)

**Setup:** Instantiate `WakeListener` with mocked `stt`, `tts`, `agent_loop`. Patch
`agent_loop.registry` with a `ToolRegistry` that has a registered `mempalace_search`
mock. Call `_try_direct_dispatch()` directly.

---

## Implementation Order

1. **9.2 — Structured logging first** (low risk, additive, self-contained)
2. **9.1.3 — MemPalace plugin tests** (fast to write, high value: confirms dispatch fix holds)
3. **9.1.1 — ContextBuilder tests** (medium complexity: memory mocking needed)
4. **9.1.2 — AgentLoop cleanup/throttle tests** (medium: needs tmp SQLite)
5. **9.3.1 — WakeListener dispatch tests** (complex: most mocking, do last)

---

## Files Created / Modified

| File | Action |
|------|--------|
| `agent/core/roamin_logging.py` | MODIFY — add JSON formatter, throttled logger, request ID |
| `tests/unit/test_roamin_logging.py` | CREATE — 9 tests |
| `tests/unit/test_context_builder.py` | CREATE — 5 tests |
| `tests/unit/test_agent_loop_cleanup.py` | CREATE — 7 tests |
| `tests/unit/test_mempalace_plugin.py` | CREATE — 10 tests |
| `tests/unit/test_wake_listener_dispatch.py` | CREATE — 5 tests |

**Total new tests: ~36**
**No existing tests modified or deleted.**

---

## Verification

```bash
# Run new tests only
python -m pytest tests/unit/ -v

# Full suite (confirm no regressions)
python -m pytest tests/ -x --ignore=tests/test_e2e_smoke.py -q

# Confirm JSON output works
python -c "
from agent.core.roamin_logging import get_json_logger, set_request_id
set_request_id('req-test-001')
log = get_json_logger('test')
log.info('Hello from JSON logger')
"
```

Expected: JSON line with `request_id: 'req-test-001'` printed to stdout/file.
