# Tasks: v15 P1/P2/P3 Reliability

> Execute in order — milestones are dependency-sorted.
> ⚠️ = Restart Roamin after this milestone.
> ✅ = Run test suite checkpoint.
> 🔍 = Verify before proceeding.

---

## Milestone 1 — Fix #6: AgentLoop Executor Non-Blocking Shutdown (P1)

- [ ] Open `agent/core/agent_loop.py`
- [ ] Locate the `with ThreadPoolExecutor(max_workers=1) as executor:` block in `_execute_step()`
- [ ] Replace context-manager pattern with explicit `executor = ThreadPoolExecutor(max_workers=1)`
- [ ] After catching `concurrent.futures.TimeoutError`: call `future.cancel()` before setting step_result
- [ ] Add `finally:` block calling `executor.shutdown(wait=False, cancel_futures=True)`
- [ ] `py_compile agent/core/agent_loop.py`
- [ ] `flake8 agent/core/agent_loop.py`
- [ ] `mypy agent/core/agent_loop.py`
- [ ] ✅ `pytest tests/test_agent_loop.py -v` (after M10 creates the file)
- [ ] ⚠️ Restart Roamin
- [ ] Commit: `fix(agent_loop): non-blocking executor shutdown on timeout (#6)`

---

## Milestone 2 — Fix #2 + #3: launch.py Health Check + Existence Guards (P2)

- [ ] Open `launch.py`
- [ ] Add `_REQUIRED_SCRIPTS` list with `run_wake_listener.py` and `run_control_api.py` paths
- [ ] Add existence check loop before any `Popen` calls — `sys.exit(...)` on missing file
- [ ] Add `_wait_for_control_api(port, timeout=15)` helper using `urllib.request.urlopen`
- [ ] Replace unconditional `"[Launcher] All systems go!"` print with the conditional health-check call
- [ ] `py_compile launch.py`
- [ ] `flake8 launch.py`
- [ ] Manual: run `python launch.py` — confirm "Control API confirmed responsive" message appears
- [ ] Commit: `fix(launch): existence guards + health-check poll before success message (#2 #3)`

---

## Milestone 3 — Fix #7: AgentLoop Status Accuracy (P2)

- [ ] Open `agent/core/agent_loop.py`
- [ ] Find `result["status"] = "completed" if result["steps"] else "blocked"` (~line 195)
- [ ] Replace with 4-way status logic: `"blocked"` / `"failed"` / `"partial"` / `"completed"`
- [ ] `py_compile agent/core/agent_loop.py`
- [ ] `flake8 agent/core/agent_loop.py`
- [ ] ✅ `pytest tests/test_agent_loop.py -v`
- [ ] Commit: `fix(agent_loop): accurate status when steps fail — partial/failed/completed (#7)`

---

## Milestone 4 — Fix #8 + #9: Raw SQLite Bypass + Import Order (P3)

- [ ] Open `agent/core/memory/memory_store.py`
- [ ] Add `cleanup_old_task_runs(older_than_hours: int = 24) -> int` method with `IF NOT EXISTS` guard on table check
- [ ] `py_compile agent/core/memory/memory_store.py`
- [ ] Open `agent/core/agent_loop.py`
- [ ] Replace `_cleanup_completed_tasks()` body — remove raw `sqlite3` import and connection, delegate to `self.store.cleanup_old_task_runs()`
- [ ] Move `import os` from inside `_execute_step()` to module-level imports at top of file (#9)
- [ ] `py_compile agent/core/agent_loop.py`
- [ ] `flake8 agent/core/agent_loop.py agent/core/memory/memory_store.py`
- [ ] ✅ `pytest tests/test_agent_loop.py tests/test_memory_module.py -v`
- [ ] Commit: `fix(agent_loop): delegate cleanup to MemoryStore, move import os to module level (#8 #9)`

---

## Milestone 5 — Fix #30: TTS Newline Escaping (P3)

- [ ] Open `agent/core/voice/tts.py`
- [ ] Find `_speak_sapi_subprocess()` — locate `safe = text.replace("'", "''")`
- [ ] Add `.replace("\n", " ").replace("\r", "")` to the escape chain
- [ ] `py_compile agent/core/voice/tts.py`
- [ ] `flake8 agent/core/voice/tts.py`
- [ ] Manual: call TTS with text containing `\n` — confirm no PowerShell crash
- [ ] Commit: `fix(tts): escape newlines in PowerShell SAPI command string (#30)`

---

## Milestone 6 — Fix #68: memory_search Fallback allow_reset (P3)

- [ ] Open `agent/core/memory/memory_search.py`
- [ ] Find the `except Exception:` fallback init block (after primary `PersistentClient` init)
- [ ] Wrap fallback in nested try/except: first try with `Settings(allow_reset=False)`, then bare fallback with warning log if `TypeError` raised
- [ ] `py_compile agent/core/memory/memory_search.py`
- [ ] `flake8 agent/core/memory/memory_search.py`
- [ ] ✅ `pytest tests/test_memory_module.py -v`
- [ ] Commit: `fix(memory_search): protect fallback init with allow_reset=False (#68)`

---

## Milestone 7 — Fix #69: Observation Privacy Check Before Capture (P3)

- [ ] Open `agent/core/observation.py`
- [ ] Locate `_capture_and_analyze()` — find the screenshot capture + OCR sequence
- [ ] 🔍 Verify `_is_privacy_window_active()` exists; if not, create it using `PRIVACY_WINDOW_TITLES`
- [ ] Move `_is_privacy_window_active()` check BEFORE `ImageGrab.grab()` call
- [ ] OCR-based `_has_sensitive_content()` check remains as secondary check after capture
- [ ] `py_compile agent/core/observation.py`
- [ ] `flake8 agent/core/observation.py`
- [ ] Commit: `fix(observation): privacy window check before screenshot capture (#69)`

---

## Milestone 8 — Fix #71 + #72: ScreenObserver Singleton + PS Injection (P3)

- [ ] Open `agent/core/screen_observer.py`
- [ ] Find `ObservationScheduler.__init__()` — add `self._observer = ScreenObserver()` as instance attribute
- [ ] Find `_worker()` — replace `observer = ScreenObserver()` (per-cycle) with `self._observer`
- [ ] Find PowerShell notification string building — locate `{msg}` interpolated into PS script
- [ ] Add `safe_msg = msg.replace('"', '\\"').replace("\n", "\`n")` before the f-string
- [ ] Replace `"{msg}"` with `"{safe_msg}"` in the PowerShell script f-string
- [ ] `py_compile agent/core/screen_observer.py`
- [ ] `flake8 agent/core/screen_observer.py`
- [ ] Commit: `fix(screen_observer): singleton ScreenObserver + escape PS notification string (#71 #72)`

---

## Milestone 9 — Test Hygiene: #99 #102 #106 #110 #111 (P3)

### #99 — test_e2e_smoke.py skip guard

- [ ] Open `tests/test_e2e_smoke.py`
- [ ] Add `import pytest` at top
- [ ] Add `pytestmark = pytest.mark.integration` module-level marker
- [ ] Add `integration` marker to `pytest.ini` under `[pytest] markers =`
- [ ] `flake8 tests/test_e2e_smoke.py`
- [ ] Confirm `pytest tests/test_e2e_smoke.py` now skips without `-m integration`

### #102 — test_model_router.py assertion

- [ ] Open `tests/test_model_router.py`
- [ ] Find `assert len(router.list_models()) >= 12`
- [ ] Replace lower bound with `>= 20` (27 models after v14 cleanup) with clear comment
- [ ] `flake8 tests/test_model_router.py`
- [ ] ✅ `pytest tests/test_model_router.py -v`

### #106 — test_control_api.py fixed sleep

- [ ] Open `tests/test_control_api.py`
- [ ] Add `_wait_for_task(client, task_id, timeout=5.0)` poll helper (0.1s retry loop)
- [ ] Replace all `time.sleep(1.4)` calls with `_wait_for_task(...)` calls
- [ ] `flake8 tests/test_control_api.py`
- [ ] ✅ `pytest tests/test_control_api.py -v`

### #110 — test_validators.py path traversal

- [ ] Open `tests/test_validators.py`
- [ ] Add `test_path_traversal_rejected` — assert `../../etc/passwd` is denied on read
- [ ] Add `test_double_encoded_traversal_rejected` — Windows-style `..\..\Windows\System32`
- [ ] `flake8 tests/test_validators.py`
- [ ] ✅ `pytest tests/test_validators.py -v`

### #111 — fixed sleeps audit

- [ ] `grep -rn "time.sleep" tests/` — list all sleep calls
- [ ] For each sleep NOT inside a poll/retry loop: replace with poll helper or `pytest-timeout` mark
- [ ] `flake8 tests/`
- [ ] ✅ Run affected test files

- [ ] Commit: `test: skip guard, model count assertion, poll helpers, path traversal, sleep audit (#99 #102 #106 #110 #111)`

---

## Milestone 10 — New Test Files: #108 + #109 (P3)

### #108 — tests/test_llama_backend.py

- [ ] Create `tests/test_llama_backend.py`
- [ ] Add `TestLlamaBackendUnit` class — fast unit tests, no GPU required
  - `test_capability_map_populated` — assert `CAPABILITY_MAP` is non-empty dict
  - `test_get_backend_raises_on_unknown_capability` — assert `RuntimeError` on bad capability
- [ ] Add `@pytest.mark.integration` class `TestLlamaBackendIntegration` with skip stub
- [ ] `flake8 tests/test_llama_backend.py`
- [ ] ✅ `pytest tests/test_llama_backend.py -v`

### #109 — tests/test_agent_loop.py

- [ ] Create `tests/test_agent_loop.py`
- [ ] Add `mock_registry` and `mock_store` fixtures
- [ ] `TestAgentLoopStatus`:
  - `test_all_steps_failed_marks_failed` — all steps raise → status is `"failed"` not `"completed"`
  - `test_no_steps_marks_blocked` — planner returns `[]` → status `"blocked"`
- [ ] `TestExecutorTimeout`:
  - `test_timeout_does_not_block_caller` — slow tool + 0.1s timeout → completes in < 1.0s wall time
- [ ] `flake8 tests/test_agent_loop.py`
- [ ] ✅ `pytest tests/test_agent_loop.py -v`
- [ ] Commit: `test(agent_loop, llama_backend): add unit test suites with integration marks (#108 #109)`

---

## Final

- [ ] ✅ Full suite: `pytest tests/test_agent_loop.py tests/test_llama_backend.py tests/test_memory_module.py tests/test_control_api.py tests/test_model_router.py tests/test_validators.py -v`
- [ ] ⚠️ Restart Roamin with all v15 changes live
- [ ] Update `.openspec.yaml` → `status: complete`, add `completed: "2026-04-12"`
- [ ] Commit: `chore: mark v15-p1-p2-p3-reliability complete`
