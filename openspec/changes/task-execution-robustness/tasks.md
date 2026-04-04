# Tasks: Task Execution Robustness

Implementation order: 4.3 → 4.1 → 4.2 → 4.4 (each validated before next)

---

## 1. Create OpenSpec

- [x] Create `openspec/changes/task-execution-robustness/.openspec.yaml`
- [x] Create `proposal.md`
- [x] Create `design.md`
- [x] Create `tasks.md` (this file)
- [x] Create `specs/feature-readiness-checks/spec.md`
- [x] Create `specs/task-deduplication/spec.md`
- [x] Create `specs/dynamic-step-prioritization/spec.md`
- [x] Create `specs/tool-fallback-chains/spec.md`

---

## 2. Implement 4.3 — Feature Readiness Checks (agent_loop.py)

- [x] Add `_check_feature_ready(capability) -> tuple[bool, str]` static method
- [x] Insert call in `run()` after `_classify_task()`, before screen observation
- [x] Verify `py_compile` passes
- [x] Verify `flake8 --max-line-length=120` passes

---

## 3. Implement 4.1 — Task Deduplication (wake_listener.py)

- [x] Add `_make_request_fingerprint(transcription) -> str` module-level function
- [x] Add `_pending_fingerprint`, `_pending_fingerprint_lock`, `_fingerprint_ttl`, `_last_fingerprint_time` to `__init__`
- [x] Add dedup check in `_on_wake()` after empty-transcription guard
- [x] Clear fingerprint in `_guarded_wake` finally block
- [x] Verify `py_compile` passes
- [x] Verify `flake8 --max-line-length=120` passes

---

## 4. Implement 4.2 — Dynamic Step Prioritization (agent_loop.py)

- [x] Add `_priority_score(step) -> int` static method
- [x] Insert `plan = sorted(plan, key=self._priority_score)` in `run()` before step loop
- [x] Verify `py_compile` passes
- [x] Verify `flake8 --max-line-length=120` passes

---

## 5. Implement 4.4 — Tool Fallback Chains (tool_registry.py)

- [x] Add `import logging` and `logger = logging.getLogger(__name__)`
- [x] Add `_TOOL_FALLBACKS` module-level constant
- [x] Extract `_execute_single()` private method
- [x] Refactor `execute()` to call `_execute_single()` and try fallbacks on failure
- [x] Verify `py_compile` passes
- [x] Verify `flake8 --max-line-length=120` passes

---

## 6. Write Tests

- [x] Create `tests/test_feature_readiness.py`
- [x] Create `tests/test_task_deduplication.py`
- [x] Create `tests/test_step_prioritization.py`
- [x] Create `tests/test_tool_fallback.py`

---

## 7. Verify

- [ ] `python -m pytest tests/test_feature_readiness.py tests/test_task_deduplication.py tests/test_step_prioritization.py tests/test_tool_fallback.py -v` — all pass
- [ ] Manual smoke: same voice query twice within 1s → second speaks "Already on it."
- [ ] Manual smoke: vision query with no mmproj → speaks readiness error immediately
- [ ] Manual smoke: block network → web_search fails → fetch_url fallback fires
