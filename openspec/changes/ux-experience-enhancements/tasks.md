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

- [ ] Add `winotify>=1.1.0` to `requirements.txt`
- [ ] Install `winotify` in venv
- [ ] Replace `_notify_windows()` body in `agent/core/screen_observer.py` with winotify + fallback
- [ ] Update `_notify` tool in `agent/core/tools.py` to pass title separately
- [ ] Verify `py_compile` passes
- [ ] Verify `flake8 --max-line-length=120` passes

---

## 3. Write Tests for 6.2

- [ ] Create `tests/test_toast_notifications.py`
- [ ] Test: winotify Notification.show() called with correct title/message
- [ ] Test: ImportError fallback to PowerShell subprocess
- [ ] Test: notify tool through ToolRegistry returns success
- [ ] Run `python -m pytest tests/test_toast_notifications.py -v` — all pass

---

## 4. Implement 6.1 — Task Progress Callbacks

- [ ] Add `on_progress` param to `AgentLoop.run()` signature
- [ ] Emit progress events: planning, executing, step_start, step_done
- [ ] Convert `for step in plan:` to `for i, step in enumerate(plan):`
- [ ] Add "Let me think..." to TTS cached phrases
- [ ] Define `_progress_handler` closure in `wake_listener._on_wake()`
- [ ] Pass `on_progress=_progress_handler` to `agent_loop.run()`
- [ ] Verify `py_compile` passes
- [ ] Verify `flake8 --max-line-length=120` passes

---

## 5. Write Tests for 6.1

- [ ] Create `tests/test_task_progress.py`
- [ ] Test: on_progress receives correct event sequence
- [ ] Test: on_progress=None works without error
- [ ] Test: cancelled task emits no progress after cancellation
- [ ] Run `python -m pytest tests/test_task_progress.py -v` — all pass

---

## 6. Implement 6.3 — Persistent Task History

- [ ] Add `task_runs` and `task_steps` tables in `memory_store._initialize_db()`
- [ ] Add `create_task_run()`, `add_task_step()`, `finish_task_run()` to MemoryStore
- [ ] Add `get_task_runs()`, `get_task_steps()`, `search_task_history()` to MemoryStore
- [ ] Add pass-through methods to MemoryManager
- [ ] Wire task logging into `AgentLoop.run()` (wrapped in try/except)
- [ ] Update `/task-history` endpoint in `control_api.py` to query SQLite
- [ ] Add `GET /task-history/{task_id}/steps` endpoint
- [ ] Verify `py_compile` passes
- [ ] Verify `flake8 --max-line-length=120` passes

---

## 7. Write Tests for 6.3

- [ ] Create `tests/test_task_history.py`
- [ ] Test: create_task_run + add_task_step + finish_task_run roundtrip
- [ ] Test: get_task_runs with since/status filters
- [ ] Test: search_task_history keyword matching
- [ ] Test: AgentLoop.run() integration — task_runs row exists after execution
- [ ] Test: /task-history API endpoint returns SQLite data
- [ ] Test: logging failure does not abort task execution
- [ ] Run `python -m pytest tests/test_task_history.py -v` — all pass

---

## 8. Verify

- [ ] Run full test suite: `python -m pytest tests/ -v` — all pass
- [ ] Run pre-commit hooks — all pass
- [ ] Manual: toast notification appears in Action Center (6.2)
- [ ] Manual: "Let me think..." spoken before planning (6.1)
- [ ] Manual: step announcements for 3+ step plans (6.1)
- [ ] Manual: task history queryable after execution (6.3)
