# Tasks: User Experience Enhancements

Implementation order: 6.2 → 6.1 → 6.3

---

## 1. Create OpenSpec

- [x] Create `.openspec.yaml`
- [x] Create `proposal.md`
- [x] Create `design.md`
- [x] Create `tasks.md` (this file)
- [x] Create `specs/toast-notifications/spec.md`
- [x] Create `specs/task-progress/spec.md`
- [x] Create `specs/task-history/spec.md`

---

## 2. Implement 6.2 — Modern Toast Notifications

- [x] Add `winotify>=1.1.0` to `requirements.txt`
- [x] Install `winotify` in venv
- [x] Replace `_notify_windows()` body in `agent/core/screen_observer.py` with winotify + fallback
- [x] Update `_notify` tool in `agent/core/tools.py` to pass title separately
- [x] Verify `py_compile` passes
- [x] Verify `flake8 --max-line-length=120` passes

---

## 3. Write Tests for 6.2

- [x] Create `tests/test_toast_notifications.py`
- [x] Test: winotify Notification.show() called with correct title/message
- [x] Test: ImportError fallback to PowerShell subprocess
- [x] Test: notify tool through ToolRegistry returns success
- [x] Run `python -m pytest tests/test_toast_notifications.py -v` — all pass (8/8)

---

## 4. Implement 6.1 — Task Progress Callbacks

- [x] Add `on_progress` param to `AgentLoop.run()` signature
- [x] Emit progress events: planning, executing, step_start, step_done
- [x] Convert `for step in plan:` to `for i, step in enumerate(plan):`
- [x] Add "Let me think..." to TTS cached phrases
- [x] Define `_progress_handler` closure in `wake_listener._on_wake()`
- [x] Pass `on_progress=_progress_handler` to `agent_loop.run()`
- [x] Verify `py_compile` passes
- [x] Verify `flake8 --max-line-length=120` passes

---

## 5. Write Tests for 6.1

- [x] Create `tests/test_task_progress.py`
- [x] Test: on_progress receives correct event sequence
- [x] Test: on_progress=None works without error
- [x] Test: cancelled task emits no progress after cancellation
- [x] Run `python -m pytest tests/test_task_progress.py -v` — all pass (5/5)

---

## 6. Implement 6.3 — Persistent Task History

- [x] Add `task_runs` and `task_steps` tables in `memory_store._initialize_db()`
- [x] Add `create_task_run()`, `add_task_step()`, `finish_task_run()` to MemoryStore
- [x] Add `get_task_runs()`, `get_task_steps()`, `search_task_history()` to MemoryStore
- [x] Add pass-through methods to MemoryManager
- [x] Wire task logging into `AgentLoop.run()` (wrapped in try/except)
- [x] Update `/task-history` endpoint in `control_api.py` to query SQLite
- [x] Add `GET /task-history/{task_id}/steps` endpoint
- [x] Verify `py_compile` passes
- [x] Verify `flake8 --max-line-length=120` passes

---

## 7. Write Tests for 6.3

- [x] Create `tests/test_task_history.py`
- [x] Test: create_task_run + add_task_step + finish_task_run roundtrip
- [x] Test: get_task_runs with since/status filters
- [x] Test: search_task_history keyword matching
- [x] Test: AgentLoop.run() integration — task_runs row exists after execution
- [x] Test: /task-history API endpoint returns SQLite data
- [x] Test: logging failure does not abort task execution
- [x] Run `python -m pytest tests/test_task_history.py -v` — all pass (14/14)

---

## 8. Verify

- [x] Run full test suite: `python -m pytest tests/ -v` — 152/152 pass
- [x] Run pre-commit hooks — all pass
- [ ] Manual: toast notification appears in Action Center (6.2)
- [ ] Manual: "Let me think..." spoken before planning (6.1)
- [ ] Manual: step announcements for 3+ step plans (6.1)
- [ ] Manual: task history queryable after execution (6.3)
