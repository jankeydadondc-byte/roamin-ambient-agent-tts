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

- [ ] Create `agent/core/validators.py` (~60 lines)
  - [ ] `validate_path(path, mode="read"|"write")` -- resolve symlinks, check against allowlist
  - [ ] `SAFE_READ_ROOTS` -- project root, user home, temp dirs
  - [ ] `SAFE_WRITE_ROOTS` -- project root, temp dirs only
  - [ ] Return structured error dict on rejection (matches existing tool error format)
- [ ] Wire `validate_path()` into `tools.py`:
  - [ ] `_read_file()` -- mode="read"
  - [ ] `_write_file()` -- mode="write"
  - [ ] `_delete_file()` -- mode="write"
  - [ ] `_move_file()` -- mode="write" (both source and dest)
  - [ ] `_glob_files()` -- mode="read"
  - [ ] `_grep_files()` -- mode="read"
  - [ ] `_list_directory()` -- mode="read"
- [ ] Verify `py_compile` passes
- [ ] Verify `flake8 --max-line-length=120` passes

---

## 3. Write Tests for 7.4

- [ ] Create `tests/test_validators.py`
- [ ] Test: path inside project root accepted (read + write)
- [ ] Test: path inside user home accepted (read only)
- [ ] Test: path outside all roots rejected
- [ ] Test: symlink resolving to unsafe path rejected
- [ ] Test: UNC path (`\\server\share`) rejected
- [ ] Test: null bytes in path rejected
- [ ] Test: relative path resolved correctly
- [ ] Run `python -m pytest tests/test_validators.py -v` -- all pass

---

## 4. Implement 7.1 -- Secrets Loader

- [ ] Add `python-dotenv>=1.0.0` to `requirements.txt`
- [ ] Install `python-dotenv` in venv
- [ ] Create `agent/core/secrets.py` (~40 lines)
  - [ ] `load_secrets()` -- load `.env` file if exists, merge with os.environ
  - [ ] `get_secret(name, required=False)` -- return value or raise if required and missing
  - [ ] `check_secrets(required_list, optional_list)` -- startup validator, logs warnings
- [ ] Create `.env.example` in project root (documents all env vars, no real values)
- [ ] Add `.env` to `.gitignore` if not already covered
- [ ] Wire `load_secrets()` into `run_wake_listener.py` early in `main()` (before component init)
- [ ] Refactor `control_api.py` to use `get_secret("ROAMIN_CONTROL_API_KEY")` instead of direct `os.environ.get()`
- [ ] Verify `py_compile` passes
- [ ] Verify `flake8 --max-line-length=120` passes

---

## 5. Write Tests for 7.1

- [ ] Create `tests/test_secrets.py`
- [ ] Test: `get_secret()` returns env var value
- [ ] Test: `get_secret(required=True)` raises on missing
- [ ] Test: `get_secret(required=False)` returns None on missing
- [ ] Test: `.env` file values loaded correctly (mock file)
- [ ] Test: env var overrides `.env` file (env takes precedence)
- [ ] Run `python -m pytest tests/test_secrets.py -v` -- all pass

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

- [ ] Create `agent/core/audit_log.py` (~50 lines)
  - [ ] `append(tool, params, result_summary, duration_ms, success)` -- write one JSON line to `logs/audit.jsonl`
  - [ ] `query(limit, tool_filter, since)` -- reverse-read JSONL with optional filters
  - [ ] Auto-prune at 100KB (reuse `_prune_log` pattern from run_wake_listener.py)
- [ ] Wire `audit_log.append()` into `tool_registry.execute()` (after tool returns, in finally block)
- [ ] Add `GET /audit-log` endpoint to `control_api.py`
  - [ ] Query params: `?limit=50&tool=run_python&since=2026-04-07`
  - [ ] Returns JSON array of audit entries
- [ ] Add `logs/audit.jsonl` to `.gitignore` (already covered by `*.log` and `logs/` patterns -- verify)
- [ ] Verify `py_compile` passes
- [ ] Verify `flake8 --max-line-length=120` passes

---

## 9. Write Tests for 7.5

- [ ] Create `tests/test_audit_log.py`
- [ ] Test: append writes valid JSON line
- [ ] Test: query returns entries in reverse chronological order
- [ ] Test: query with tool_filter returns only matching entries
- [ ] Test: query with since filter works
- [ ] Test: auto-prune triggers at size limit
- [ ] Test: append failure does not crash tool execution
- [ ] Run `python -m pytest tests/test_audit_log.py -v` -- all pass

---

## 10. Implement 7.2 -- Response Size Limit

- [ ] Add `MAX_RESPONSE_BYTES = 256 * 1024` constant to `model_router.py`
- [ ] In HTTP fallback path: check `len(response.content)` before parsing JSON
- [ ] If exceeded: log warning, truncate response text, return error to caller
- [ ] Verify `py_compile` passes

---

## 11. Write Tests for 7.2

- [ ] Add test to `tests/test_model_router.py` (or new file)
- [ ] Test: normal-size response passes through
- [ ] Test: oversized response returns error (mock HTTP response)
- [ ] Run relevant tests -- all pass

---

## 12. Integration & Verification

- [ ] Run full test suite: `python -m pytest tests/ -v` -- all pass
- [ ] Run pre-commit hooks -- all pass
- [ ] Manual: attempt `write_file` to `C:\Windows\System32\test.txt` -- rejected by validator
- [ ] Manual: `run_python` triggers approval toast -- approve works, deny works
- [ ] Manual: `logs/audit.jsonl` contains entries after tool execution
- [ ] Manual: `GET /audit-log` returns data in Control Panel
- [ ] Manual: `.env` file loaded at startup (add test key, verify in logs)
- [ ] Update MASTER_CONTEXT_PACK.md with Phase 7 completion status
