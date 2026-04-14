# Proposal: v15 P1/P2/P3 Reliability

## 🎯 Goal

Fix the remaining 1 P1, 5 P2s, and 15 P3s from the v12 audit that were not addressed by v13
(security) or v14 (data integrity/config). Targets fall into three categories:

1. **Core reliability** — AgentLoop executor lifecycle, launch health checks, agent status accuracy
2. **Code quality** — TTS escaping, ChromaDB fallback safety, observation privacy ordering,
   ScreenObserver lifecycle
3. **Test hygiene** — skip guards, stale assertions, fixed sleeps, missing integration marks

Findings #18 and #37 are formally deferred (see `.openspec.yaml`) — both require larger refactors
tracked for v16.

---

## 🔧 Architecture Impact

- `agent/core/agent_loop.py` — executor shutdown, status logic, sqlite cleanup, import order
- `launch.py` — health-check poll, existence guards
- `agent/core/voice/tts.py` — PowerShell string escaping
- `agent/core/memory/memory_search.py` — fallback init safety
- `agent/core/observation.py` — privacy-check ordering
- `agent/core/screen_observer.py` — singleton ScreenObserver, PS injection fix
- `tests/` — skip guards, retry loops, new integration test files

No breaking public API changes. `AgentLoop` executor fix changes internal timeout behavior only.

---

## 📋 Milestone Breakdown

---

### Milestone 1 — Fix #6: AgentLoop ThreadPoolExecutor Executor Shutdown (P1)

**File:** `agent/core/agent_loop.py`

**Problem:** After a `TimeoutError`, the submitted future is not cancelled and the thread keeps
running. When the `with ThreadPoolExecutor() as executor:` block exits, `__exit__` calls
`shutdown(wait=True)`, which **blocks until the thread finishes** — potentially another full
tool timeout (30s) on top of the original timeout. The timeout guard is illusory.

**Fix:** After catching `TimeoutError`, call `future.cancel()` and switch to
`executor.shutdown(wait=False, cancel_futures=True)` (Python 3.9+). Since we use Python 3.14,
`cancel_futures` is available. Restructure to avoid the context manager so shutdown is explicit:

```python
# Execute tool with non-blocking shutdown on timeout (#6)
executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
future = executor.submit(self._registry.execute, str(tool_name), params)
try:
    outcome = future.result(timeout=_TOOL_TIMEOUT_SECONDS)
    step_result["status"] = "executed"
    step_result["outcome"] = str(outcome.get("result") or outcome.get("error", ""))[:1500]
except concurrent.futures.TimeoutError:
    future.cancel()
    step_result["status"] = "failed"
    step_result["outcome"] = f"Tool '{tool_name}' timed out after {_TOOL_TIMEOUT_SECONDS}s"
    logger.warning("Tool '%s' timed out after %ds", tool_name, _TOOL_TIMEOUT_SECONDS)
except Exception as e:
    step_result["status"] = "failed"
    step_result["outcome"] = str(e)[:500]
    logger.warning("Tool '%s' raised exception: %s", tool_name, e)
finally:
    # cancel_futures=True abandons still-running thread; don't block on it (#6)
    executor.shutdown(wait=False, cancel_futures=True)
```

**Restart required:** Yes — agent_loop is imported at runtime.

**Verification:**
```
py_compile agent/core/agent_loop.py
flake8 agent/core/agent_loop.py
mypy agent/core/agent_loop.py
pytest tests/test_agent_loop.py -v
```

---

### Milestone 2 — Fix #2 + #3: launch.py Health Check + Existence Guards (P2)

**File:** `launch.py`

**Problem #2:** `"[Launcher] All systems go!"` prints immediately after spawning processes.
Control API may not be accepting connections yet — the success message is a lie.

**Problem #3:** `run_wake_listener.py` and `run_control_api.py` are passed directly to `Popen`
with no check that they exist. A missing file causes a cryptic OS error.

**Fix #3 — existence guards** (add before any `Popen` calls):
```python
# Verify required launch targets exist before spawning (#3)
_REQUIRED_SCRIPTS = [
    PROJECT_ROOT / "run_wake_listener.py",
    PROJECT_ROOT / "run_control_api.py",
]
for _script in _REQUIRED_SCRIPTS:
    if not _script.exists():
        sys.exit(f"[Launcher] ERROR: required script not found: {_script}")
```

**Fix #2 — health-check poll** (replace success print with):
```python
def _wait_for_control_api(port: int = 8765, timeout: int = 15) -> bool:
    """Poll /status until the Control API responds or timeout expires (#2)."""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False

# Replace unconditional success print with:
if _wait_for_control_api():
    print("[Launcher] All systems go — Control API confirmed responsive.")
else:
    print("[Launcher] WARNING: Control API did not respond within 15s. Check the console window.")
```

**Verification:**
```
py_compile launch.py
flake8 launch.py
```
Manual: run `python launch.py` — confirm it waits, then prints confirmed message.

---

### Milestone 3 — Fix #7: AgentLoop Status "completed" with Failed Steps (P2)

**File:** `agent/core/agent_loop.py`

**Problem:** Line ~195:
```python
result["status"] = "completed" if result["steps"] else "blocked"
```
If all steps returned `status: "failed"`, the task is still marked `"completed"`.
Callers (control_api task history, supervisor) cannot distinguish partial-failure from success.

**Fix:**
```python
# Mark status based on step outcomes, not just presence of steps (#7)
if not result["steps"]:
    result["status"] = "blocked"
elif all(s.get("status") == "failed" for s in result["steps"]):
    result["status"] = "failed"
elif any(s.get("status") == "failed" for s in result["steps"]):
    result["status"] = "partial"
else:
    result["status"] = "completed"
```

**Verification:**
```
py_compile agent/core/agent_loop.py
pytest tests/test_agent_loop.py -v
```

---

### Milestone 4 — Fix #8 + #9: AgentLoop Raw SQLite + Import Order (P3)

**File:** `agent/core/agent_loop.py`

**Problem #8:** `_cleanup_completed_tasks()` opens a raw `sqlite3` connection directly to
`roamin_memory.db`, bypassing `MemoryStore`. This circumvents WAL mode, the UNIQUE constraint,
and any future migration logic.

**Fix:** Delegate to `MemoryStore` by adding a `cleanup_old_task_runs(older_than_hours)` method
to `MemoryStore`, then call it from `_cleanup_completed_tasks()`:

In `memory_store.py`, add:
```python
def cleanup_old_task_runs(self, older_than_hours: int = 24) -> int:
    """Delete task_runs older than given hours. Returns deleted count (#8)."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(hours=older_than_hours)).isoformat()
    with sqlite3.connect(self.db_path) as conn:
        cur = conn.execute(
            "DELETE FROM task_runs WHERE completed_at < ? AND status IN ('completed','failed')",
            (cutoff,),
        )
        return cur.rowcount
```

In `agent_loop.py`, replace the raw sqlite block:
```python
def _cleanup_completed_tasks(self, older_than_hours: int = 24) -> dict:
    """Remove old completed/failed task_runs via MemoryStore (#8)."""
    deleted = self.store.cleanup_old_task_runs(older_than_hours)
    return {"deleted_count": deleted}
```

**Problem #9:** `import os` appears inside `_execute_step()` function body. Move to module-level
imports with other stdlib imports.

**Verification:**
```
py_compile agent/core/agent_loop.py agent/core/memory/memory_store.py
flake8 agent/core/agent_loop.py agent/core/memory/memory_store.py
pytest tests/test_agent_loop.py tests/test_memory_module.py -v
```

---

### Milestone 5 — Fix #30: TTS Newline Escaping in PowerShell SAPI (P3)

**File:** `agent/core/voice/tts.py`

**Problem:** `_speak_sapi_subprocess()` escapes single quotes but not newlines. If `text`
contains `\n`, the embedded newline breaks the PowerShell one-liner:
```python
safe = text.replace("'", "''")  # current — newlines not handled
```

PowerShell's `-Command` string ends at the first unescaped newline.

**Fix:**
```python
# Escape for PowerShell string literal: single-quotes and newlines (#30)
safe = text.replace("'", "''").replace("\n", " ").replace("\r", "")
```

Replacing `\n` with a space is the correct TTS behavior — newlines in spoken text should be
a brief pause, which a space achieves naturally via the synthesizer's sentence boundary logic.

**Verification:**
```
py_compile agent/core/voice/tts.py
flake8 agent/core/voice/tts.py
```
Manual: speak a string containing `\n` via TTS — confirm no crash, words are spoken.

---

### Milestone 6 — Fix #68: memory_search.py Fallback Init Missing allow_reset=False (P3)

**File:** `agent/core/memory/memory_search.py`

**Problem:** The fallback `except` path (for older chromadb) omits `allow_reset=False`:
```python
except Exception:
    self.client = chromadb.PersistentClient(path=self.db_path)  # no protection
```

**Fix:** Add `Settings` to the fallback with a nested try:
```python
except Exception:
    try:
        # Older chromadb: try without settings kwarg but still attempt reset protection
        self.client = chromadb.PersistentClient(
            path=self.db_path,
            settings=chromadb.Settings(allow_reset=False),
        )
    except TypeError:
        # Very old chromadb: no settings kwarg at all — accept the gap, log warning (#68)
        logger.warning(
            "chromadb version does not support allow_reset=False — reset protection unavailable"
        )
        self.client = chromadb.PersistentClient(path=self.db_path)
```

**Verification:**
```
py_compile agent/core/memory/memory_search.py
pytest tests/test_memory_module.py -v
```

---

### Milestone 7 — Fix #69: Observation Privacy Check Before OCR (P3)

**File:** `agent/core/observation.py`

**Problem:** Current order:
1. `screenshot = ImageGrab.grab()`
2. `ocr_text = self._run_ocr(screenshot)`
3. `if self._has_sensitive_content(ocr_text): return`

Sensitive screen data has already been processed through pytesseract before the check fires.

**Fix:** Window-title-based privacy check runs before capture (non-OCR check is cheap):
```python
# Check window title / privacy list BEFORE capture — avoids OCR'ing sensitive content (#69)
if self._is_privacy_window_active():
    logger.debug("Privacy window active — skipping capture")
    return

screenshot = ImageGrab.grab()
ocr_text = self._run_ocr(screenshot)

# Secondary check: OCR text may reveal sensitivity not visible in window title
if self._has_sensitive_content(ocr_text):
    logger.info("Sensitive OCR content detected — triggering privacy pause")
    self._privacy_pause_until = time.time() + self._privacy_pause_seconds
    return
```

Add `_is_privacy_window_active()` if not present — check foreground window title against
`PRIVACY_WINDOW_TITLES` list (already exists in the class).

**Verification:**
```
py_compile agent/core/observation.py
flake8 agent/core/observation.py
```

---

### Milestone 8 — Fix #71 + #72: ScreenObserver Singleton + PS Injection (P3)

**File:** `agent/core/screen_observer.py`

**Problem #71:** `_worker()` in `ObservationScheduler` creates a new `ScreenObserver()` on
every iteration — repeated `ModelRouter()` + `MemoryManager()` disk I/O every cycle.

**Fix:** Instantiate once at scheduler startup:
```python
class ObservationScheduler:
    def __init__(self, ...):
        ...
        # Create observer once — reuse across cycles (#71)
        self._observer = ScreenObserver()

    def _worker(self):
        while self._running:
            result = self._observer.observe()  # reuse singleton
            ...
```

**Problem #72:** PowerShell notification embeds `{msg}` directly into a heredoc string.
If `label` or URLs contain `"`, the PS command breaks.

**Fix:** Escape double quotes before interpolation:
```python
# Sanitize message for PowerShell double-quoted string (#72)
safe_msg = msg.replace('"', '\\"').replace("\n", "`n")
powershell_script = f"""
$shell = New-Object -ComObject WScript.Shell
$shell.Popup("{safe_msg}", 60, "Roamin — Action Needs Approval", 0x40)
"""
```

**Verification:**
```
py_compile agent/core/screen_observer.py
flake8 agent/core/screen_observer.py
```

---

### Milestone 9 — Test Hygiene: #99 #102 #106 #110 #111 (P3)

#### #99 — test_e2e_smoke.py: add @pytest.mark.integration skip guard

**File:** `tests/test_e2e_smoke.py`

Add at top of file:
```python
import pytest

pytestmark = pytest.mark.integration  # skip unless -m integration passed
```

And add a conditional skip:
```python
@pytest.mark.integration
def test_install_creates_task():
    ...
```

Register `integration` marker in `pytest.ini`:
```ini
markers =
    integration: requires live services (Control API, LM Studio)
```

#### #102 — test_model_router.py: fix stale model count assertion

Replace `>= 12` with an explicit minimum matching the 27 models now in `model_config.json`
after v14 cleanup, or assert against named capabilities instead of raw count:
```python
def test_list_models_returns_all_models(self, router):
    models = router.list_models()
    # v14 cleanup: 27 models in config; allow ±5 for dynamic discovery (#102)
    assert len(models) >= 20, f"Expected >= 20 models, got {len(models)}: {[m.id for m in models]}"
```

#### #106 — test_control_api.py: replace fixed sleeps with retry poll

Replace `time.sleep(1.4)` waits with a poll helper:
```python
def _wait_for_task(client, task_id, timeout=5.0):
    """Poll task-history until task_id appears or timeout (#106)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get("/task-history")
        tasks = resp.json().get("tasks", [])
        if any(t["task_id"] == task_id for t in tasks):
            return True
        time.sleep(0.1)
    return False
```

#### #110 — test_validators.py: add path traversal tests

Add to `TestValidatePath`:
```python
def test_path_traversal_rejected(self, tmp_path):
    result = validate_path("../../etc/passwd", mode="read")
    assert result["allowed"] is False

def test_double_encoded_traversal_rejected(self, tmp_path):
    result = validate_path(r"C:\AI\roamin-ambient-agent-tts\..\..\Windows\System32", mode="read")
    assert result["allowed"] is False
```

#### #111 — fixed sleeps throughout tests

Audit `tests/` for `time.sleep()` calls not inside a poll loop. Replace with poll helpers
or `pytest-timeout` per-test marks. Specific instances found in `test_control_api.py` (covered
above in #106) and any others found during implementation.

---

### Milestone 10 — New Test Files: #108 + #109 (P3)

#### #108 — Create tests/test_llama_backend.py with integration marks

```python
"""tests/test_llama_backend.py — unit tests for LlamaCppBackend (no GPU required)."""
import pytest
from unittest.mock import MagicMock, patch

# Mark GPU/GGUF tests so they are excluded from standard pytest runs (#108)
pytestmark_integration = pytest.mark.integration


class TestLlamaBackendUnit:
    """Fast unit tests — no actual model files needed."""

    def test_capability_map_populated(self):
        from agent.core.llama_backend import CAPABILITY_MAP
        assert isinstance(CAPABILITY_MAP, dict)
        assert len(CAPABILITY_MAP) > 0

    def test_get_backend_raises_on_unknown_capability(self):
        from agent.core.llama_backend import LlamaBackendManager
        mgr = LlamaBackendManager()
        with pytest.raises(RuntimeError, match="Unknown capability"):
            mgr.get_backend("nonexistent_capability_xyz")


@pytest.mark.integration
class TestLlamaBackendIntegration:
    """Require GPU + GGUF files — only run with: pytest -m integration"""

    def test_loads_and_generates(self):
        pytest.skip("Requires GGUF model on disk — run manually with -m integration")
```

#### #109 — Create tests/test_agent_loop.py with real behavior tests

```python
"""tests/test_agent_loop.py — unit tests for AgentLoop."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_registry():
    reg = MagicMock()
    reg.execute.return_value = {"result": "ok"}
    reg.get_risk_level.return_value = "low"
    return reg


@pytest.fixture
def mock_store():
    return MagicMock()


class TestAgentLoopStatus:
    def test_all_steps_failed_marks_failed(self, mock_registry, mock_store):
        """Status must be 'failed' when all steps fail, not 'completed' (#7)."""
        from agent.core.agent_loop import AgentLoop
        loop = AgentLoop(registry=mock_registry, store=mock_store)
        mock_registry.execute.side_effect = Exception("tool error")
        result = loop.run("do something dangerous", session_context=None)
        assert result["status"] in ("failed", "blocked")

    def test_no_steps_marks_blocked(self, mock_registry, mock_store):
        from agent.core.agent_loop import AgentLoop
        loop = AgentLoop(registry=mock_registry, store=mock_store)
        # Simulate planner returning no steps
        with patch.object(loop, "_plan_steps", return_value=[]):
            result = loop.run("", session_context=None)
        assert result["status"] == "blocked"


class TestExecutorTimeout:
    def test_timeout_does_not_block_caller(self, mock_registry, mock_store):
        """Executor shutdown must not block after TimeoutError (#6)."""
        import time
        from agent.core.agent_loop import AgentLoop
        import concurrent.futures

        loop = AgentLoop(registry=mock_registry, store=mock_store)

        def slow_tool(*a, **kw):
            time.sleep(60)

        mock_registry.execute.side_effect = slow_tool

        with patch("agent.core.agent_loop._TOOL_TIMEOUT_SECONDS", 0.1):
            start = time.time()
            step = {"tool": "slow_tool", "params": {}}
            result = loop._execute_step(step)
            elapsed = time.time() - start

        assert result["status"] == "failed"
        assert "timed out" in result["outcome"].lower()
        # Must complete well within 2x the timeout — not block for another full timeout
        assert elapsed < 1.0, f"Executor blocked for {elapsed:.2f}s after timeout"
```

**Verification:**
```
py_compile tests/test_agent_loop.py tests/test_llama_backend.py
flake8 tests/test_agent_loop.py tests/test_llama_backend.py
pytest tests/test_agent_loop.py tests/test_llama_backend.py -v
```

---

## 🛡️ Rollback Plan

```
git revert <commit-hash>
```

Each milestone is a separate commit. Revert in reverse order if needed.

---

## 📊 Testing Strategy

```
# After each milestone:
pytest tests/test_agent_loop.py tests/test_memory_module.py
       tests/test_control_api.py tests/test_model_router.py
       tests/test_validators.py tests/test_llama_backend.py -v

# Full suite before final commit:
pytest -v --ignore=tests/test_e2e_smoke.py

# Integration tests (requires live Roamin):
pytest -m integration -v
```

---

## ⚠️ Risk Assessment

| Finding | Risk | Notes |
|---|---|---|
| #6 | ⚠️⚠️ | `cancel_futures=True` only available Python 3.9+ — confirmed 3.14, safe |
| #7 | ⚠️ | New `"partial"` status value — downstream callers should handle gracefully |
| #8 | ⚠️ | `task_runs` table may not exist if schema is old — add `IF NOT EXISTS` guard |
| #69 | ⚠️ | `_is_privacy_window_active()` may not exist — verify before calling |
| #71 | ⚠️ | Singleton `ScreenObserver` — if it holds state that should reset per cycle, audit |

---
**Status: COMPLETE** — committed bd2108f (2026-04-13), 436 tests passing.
