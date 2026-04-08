# Tasks: Security & Integration Hardening (Priority 7)

Implementation order: 7.4 (validators) --> 7.1 (secrets) --> 7.3 (approval gates) --> 7.5 (audit log) --> 7.2 (response limits)

Validators first because approval gates and audit logging both depend on clean validation.

---

## 1. Create OpenSpec

- [x] Create `.openspec.yaml`
- [x] Create `proposal.md`
- [x] Create `design.md`
- [x] Create `tasks.md` (this file)

---

## 2. Implement 7.4 -- Path & Command Validators

- [x] Create `agent/core/validators.py` (~70 lines)
  - [x] `validate_path(path, mode="read"|"write")` -- resolve symlinks, check against allowlist
  - [x] `SAFE_READ_ROOTS` -- project root, user home, temp dirs
  - [x] `SAFE_WRITE_ROOTS` -- project root, temp dirs only
  - [x] Return structured error dict on rejection (matches existing tool error format)
- [x] Wire `validate_path()` into `tools.py`:
  - [x] `_read_file()` -- mode="read"
  - [x] `_write_file()` -- mode="write"
  - [x] `_delete_file()` -- mode="write"
  - [x] `_move_file()` -- mode="write" (both source and dest)
  - [x] `_glob_files()` -- mode="read"
  - [x] `_grep_files()` -- mode="read"
  - [x] `_list_directory()` -- mode="read"
- [x] Verify `py_compile` passes
- [x] Verify `flake8 --max-line-length=120` passes

---

## 3. Write Tests for 7.4

- [x] Create `tests/test_validators.py`
- [x] Test: path inside project root accepted (read + write)
- [x] Test: path inside user home accepted (read only)
- [x] Test: path outside all roots rejected
- [x] Test: UNC path (`\\server\share`) rejected
- [x] Test: null bytes in path rejected
- [x] Test: relative path resolved correctly
- [x] Test: mode read allows more roots than write
- [x] Run `python -m pytest tests/test_validators.py -v` -- 12/12 pass

---

## 4. Implement 7.1 -- Secrets Loader

- [x] Create `agent/core/secrets.py` (~67 lines) -- manual .env parser (no python-dotenv dep needed)
  - [x] `load_secrets()` -- load `.env` file if exists, merge with os.environ
  - [x] `get_secret(name, required=False)` -- return value or raise if required and missing
  - [x] `check_secrets(required_list, optional_list)` -- startup validator, logs warnings
- [x] Create `.env.example` in project root (documents all env vars, no real values)
- [x] Add `.env` to `.gitignore`
- [x] Wire `load_secrets()` into `run_wake_listener.py` early in `main()` (before component init)
- [x] Refactor `control_api.py` to use `get_secret("ROAMIN_CONTROL_API_KEY")` instead of direct `os.environ.get()`
- [x] Verify `py_compile` passes
- [x] Verify `flake8 --max-line-length=120` passes

---

## 5. Write Tests for 7.1

- [x] Create `tests/test_secrets.py`
- [x] Test: `get_secret()` returns env var value
- [x] Test: `get_secret(required=True)` raises on missing
- [x] Test: `get_secret(required=False)` returns None on missing
- [x] Test: `.env` file values loaded correctly (mock file)
- [x] Test: env var overrides `.env` file (env takes precedence)
- [x] Test: missing .env file no error
- [x] Test: check_secrets required missing raises
- [x] Test: check_secrets required present ok
- [x] Test: check_secrets optional missing no error
- [x] Run `python -m pytest tests/test_secrets.py -v` -- 11/11 pass

---

## 6. Implement 7.3 -- Approval Gates for High-Risk Tools

- [ ] Add pre-execution hook to `tool_registry.execute()`:
  - [ ] Check tool's `risk` field
  - [ ] If `risk == "high"` and approval not pre-granted: create pending_approval entry
  - [ ] Fire toast notification with tool name + param summary
  - [ ] Block execution until approved/denied/timeout (60s)
  - [ ] Return structured error on deny or timeout
- [ ] Add `approval_required` flag to tool registration (default: follows risk level)
- [ ] Add `--no-approval` flag or env var `ROAMIN_SKIP_APPROVAL=1` for dev/testing bypass
- [ ] Verify existing HITL tests still pass
- [ ] Verify `py_compile` passes
- [ ] Verify `flake8 --max-line-length=120` passes

---

## 7. Write Tests for 7.3

- [ ] Create `tests/test_approval_gates.py`
- [ ] Test: low-risk tool executes immediately (no approval)
- [ ] Test: high-risk tool creates pending_approval entry
- [ ] Test: approved tool executes after approval
- [ ] Test: denied tool returns structured error
- [ ] Test: timeout returns structured error
- [ ] Test: `ROAMIN_SKIP_APPROVAL=1` bypasses approval
- [ ] Run `python -m pytest tests/test_approval_gates.py -v` -- all pass

---

## 8. Implement 7.5 -- Audit Log

- [x] Create `agent/core/audit_log.py` (~100 lines)
  - [x] `append(tool, params, result_summary, duration_ms, success)` -- write one JSON line to `logs/audit.jsonl`
  - [x] `query(limit, tool_filter, since)` -- reverse-read JSONL with optional filters
  - [x] Auto-prune at 100KB
  - [x] `_sanitize_params()` -- truncate large values, redact sensitive fields
- [x] Wire `audit_log.append()` into `tool_registry.execute()` (tracks primary, fallback, and failure)
- [x] Add `GET /audit-log` endpoint to `control_api.py`
  - [x] Query params: `?limit=50&tool=run_python&since=2026-04-07`
  - [x] Returns JSON object with entries array and count
- [x] `logs/audit.jsonl` covered by existing `.gitignore` (`logs/` pattern)
- [x] Verify `py_compile` passes
- [x] Verify `flake8 --max-line-length=120` passes

---

## 9. Write Tests for 7.5

- [x] Create `tests/test_audit_log.py`
- [x] Test: append writes valid JSON line
- [x] Test: append multiple entries
- [x] Test: append truncates large result
- [x] Test: append sanitizes large params
- [x] Test: append failure does not raise
- [x] Test: query returns entries in reverse chronological order
- [x] Test: query with tool_filter returns only matching entries
- [x] Test: query with since filter works
- [x] Test: query respects limit
- [x] Test: query empty log returns empty list
- [x] Test: prune triggers on large file
- [x] Run `python -m pytest tests/test_audit_log.py -v` -- 11/11 pass

---

## 10. Implement 7.2 -- Response Size Limit

- [x] In HTTP fallback path of `model_router.py`: check `len(response.content) > 256 * 1024`
- [x] If exceeded: raise RuntimeError with size details
- [x] Verify `py_compile` passes

---

## 11. Write Tests for 7.2

- [ ] Add test to `tests/test_model_router.py` (or new file)
- [ ] Test: normal-size response passes through
- [ ] Test: oversized response returns error (mock HTTP response)
- [ ] Run relevant tests -- all pass

---

## 12. Integration & Verification

- [x] Run full test suite: `python -m pytest tests/ -v` -- 206/208 pass (2 pre-existing failures unrelated to security work)
- [x] Run pre-commit hooks -- all pass
- [ ] Manual: attempt `write_file` to `C:\Windows\System32\test.txt` -- rejected by validator
- [ ] Manual: `run_python` triggers approval toast -- approve works, deny works (BLOCKED: approval gates not yet wired, task 6)
- [ ] Manual: `logs/audit.jsonl` contains entries after tool execution
- [ ] Manual: `GET /audit-log` returns data in Control Panel
- [ ] Manual: `.env` file loaded at startup (add test key, verify in logs)
- [ ] Update MASTER_CONTEXT_PACK.md with Phase 7 completion status
