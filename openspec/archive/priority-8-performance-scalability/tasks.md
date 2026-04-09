# Tasks: Priority 8 — Performance & Scalability Optimization

## Implementation Plan (Sequential)

### Milestone 1: Asynchronous Task Execution

#### Subtasks:

1. ✅ **1.1 Create `agent/core/async_utils.py`**
   - Implement `AsyncRetryError` exception class
   - Implement `async_retry()` with exponential backoff (max_retries=2, delay=1.0s)
   - Implement `async_web_search()` using `loop.run_in_executor()` for ddgs search
   - Add type hints and docstrings

2. ✅ **1.2 Refactor `agent/core/agent_loop.py`**
   - Replace `_execute_step()` with `_execute_step_async()`
   - Use `asyncio.gather(*tasks)` for parallel execution
   - Check resource exhaustion before each step (throttle if exhausted)
   - Add feature flag check: `ROAMIN_USE_ASYNC` (default off)

3. ✅ **1.3 Update AgentLoop.run()**
   - Wrap all steps in async context
   - Handle exceptions per-step (don't abort entire plan on single failure)
   - Return list of results with error details

4. ✅ **1.4 Add unit tests**
   - `test_async_retry_success()` — verify successful retry
   - `test_async_retry_exhausted()` — verify exception after max retries
   - `test_async_web_search_returns_results()` — verify ddgs integration

#### Acceptance Criteria:

- [x] No blocking I/O in async path (web search, file reads)
- [x] async_retry() with exponential backoff implemented
- [x] Feature flag `ROAMIN_USE_ASYNC` defaults to off
- [x] All 4 unit tests passing

---

### Milestone 2: Resource Monitoring & Throttling

#### Subtasks:

1. ✅ **2.1 Create `agent/core/resource_monitor.py`**
   - Implement `get_cpu_percent(interval=0.5)`
   - Implement `get_ram_usage_mb()`
   - Implement `get_vram_usage_mb()` using nvidia-smi
   - Implement `is_resource_exhausted(threshold_cpu=90, threshold_ram_mb=16000)`
   - Implement `get_throttle_status()` for `/health` endpoint

2. ✅ **2.2 Integrate with AgentLoop**
   - Add `_should_throttle()` method to check resource exhaustion
   - Call `_should_throttle()` before each step execution
   - Return throttled error if resources exhausted (max 3 retries)

3. ✅ **2.3 Add `/health` endpoint to Control API**
   - GET `/health` returns `{cpu_percent, ram_mb, vram_mb, throttled}`
   - Use `get_throttle_status()` from resource_monitor.py
   - Include timestamp in response

4. ✅ **2.4 Add unit tests**
   - `test_cpu_percent_returns_valid_value()`
   - `test_ram_usage_returns_positive_mb()`
   - `test_is_resource_exhausted_thresholds()`

#### Acceptance Criteria:

- [x] `/health` endpoint returns CPU/RAM/VRAM + throttle status — verified manually (cpu_percent: 16.9, ram_mb: 26173, vram_mb: 9786, throttled: true)
- [x] Throttle check gated behind ROAMIN_USE_ASYNC=1 (fail-open, never blocks execution on monitoring failure)
- [x] All 9 unit tests passing

---

### Milestone 3: Background Task Cleanup

#### Subtasks:

1. ✅ **3.1 Add cleanup method to AgentLoop**
   - Implement `_cleanup_completed_tasks(older_than_hours=24)`
   - Delete completed tasks older than cutoff timestamp
   - Return `{deleted_count, oldest_retained_ts}`

2. ✅ **3.2 Schedule cleanup in run_wake_listener.py**
   - Use `schedule.every(5).minutes.do(_cleanup_completed_tasks)`
   - Run in background thread (non-blocking)

3. ✅ **3.3 Add `/actions/cleanup-tasks` endpoint**
   - POST `/actions/cleanup-tasks?older_than_hours=24`
   - Returns `{deleted_count, oldest_retained_ts}`

4. ✅ **3.4 Add unit tests**
   - `test_cleanup_deletes_old_tasks()`
   - `test_cleanup_keeps_recent_tasks()`

#### Acceptance Criteria:

- [x] Cleanup runs every 5 minutes (background thread in run_wake_listener.py)
- [x] `POST /actions/cleanup-tasks` endpoint wired in control_api.py
- [x] Old tasks (>24h) deleted, recent tasks preserved

---

## Verification Checklist

### Static Analysis

```bash
# Validate Python syntax
C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python.exe -m py_compile agent/core/async_utils.py
C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python.exe -m py_compile agent/core/resource_monitor.py

# Linting (max-line-length=120)
C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python.exe -m flake8 agent/core/async_utils.py --max-line-length=120
C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python.exe -m flake8 agent/core/resource_monitor.py --max-line-length=120

# Type checking
C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python.exe -m mypy agent/core/async_utils.py
```

### Unit Tests

```bash
# Run new tests
C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python.exe -m pytest tests/unit/test_async_utils.py -v
C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python.exe -m pytest tests/unit/test_resource_monitor.py -v
```

### Integration Tests

```bash
# Start Control API and test /health endpoint
start-process wscript.exe -ArgumentList '"C:\AI\roamin-ambient-agent-tts\_start_wake_listener.vbs"' -WindowStyle Hidden

# Test /health endpoint
curl http://127.0.0.1:8765/health

# Expected output:
# {"cpu_percent": 15.2, "ram_mb": 4096, "vram_mb": 5120, "throttled": false}
```

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| **asyncio.gather() causes crashes** | Feature flag `ROAMIN_USE_ASYNC` (default off) → gradual rollout |
| **Resource monitor import fails** | Graceful fallback (no throttling, but agent continues) |
| **SQLite cleanup locks database** | Use connection timeout (5s), retry on lock |

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

## Acceptance Criteria (Final)

- [x] All Milestones 1–3 implemented and committed — commit 2418cfa, pushed to main
- [x] 13 new unit tests passing (tests/unit/test_async_utils.py + test_resource_monitor.py)
- [x] `/health` endpoint verified manually — returns all 5 fields correctly
- [ ] Control Panel "Health" tab — deferred (API endpoint exists, UI tab not built yet)
- [x] OpenSpec proposal archived to `openspec/archive/priority-8-performance-scalability/`

---

## Notes & Constraints

- PS5.1 ONLY — no `&&`, no `||`, no `?:` in PowerShell
- Python changes require `py_compile + flake8 --max-line-length=120`
- Use `Path(__file__).parent` for all paths (no hardcoded absolute paths)
- No debug print() in committed code
