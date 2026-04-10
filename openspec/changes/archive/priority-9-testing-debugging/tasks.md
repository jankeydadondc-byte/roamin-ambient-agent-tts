# Priority 9 Tasks — Testing & Debugging

## Milestone 9.2 — Structured Logging

- [ ] 9.2.1 Add `JsonFormatter` class to `roamin_logging.py`
- [ ] 9.2.2 Add `ThrottledLogger` class to `roamin_logging.py`
- [ ] 9.2.3 Add `_request_id_var`, `set_request_id`, `get_request_id`, `bind_request_id` to `roamin_logging.py`
- [ ] 9.2.4 Add `get_json_logger(name, log_file=None)` factory to `roamin_logging.py`
- [ ] 9.2.5 Create `tests/unit/test_roamin_logging.py` (9 tests)

## Milestone 9.1 — Unit Tests for Uncovered Core Modules

- [ ] 9.1.3 Create `tests/unit/test_mempalace_plugin.py` (10 tests)
- [ ] 9.1.1 Create `tests/unit/test_context_builder.py` (5 tests)
- [ ] 9.1.2 Create `tests/unit/test_agent_loop_cleanup.py` (7 tests)

## Milestone 9.3 — Error Recovery Testing (Gap Fill)

- [ ] 9.3.1 Create `tests/unit/test_wake_listener_dispatch.py` (5 tests)

## Verification

- [ ] All new unit tests pass: `python -m pytest tests/unit/ -v`
- [ ] No regressions in full suite: `python -m pytest tests/ -x --ignore=tests/test_e2e_smoke.py -q`
- [ ] JSON logger smoke test passes (see proposal.md)
