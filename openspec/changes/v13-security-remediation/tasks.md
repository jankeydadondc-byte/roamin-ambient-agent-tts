# Tasks: v13 Security Remediation

> Execute in order — each milestone is dependency-sorted.
> ⚠️ = Restart Roamin after this step before proceeding.
> ✅ = Run test suite after this step.

---

## Pre-Flight
- [x] `git status` — confirm clean working tree before starting
- [x] `git log --oneline -3` — note current HEAD for rollback reference
- [x] Back up `.bak` copies: `tool_registry.py.bak`, `validators.py.bak`, `control_api.py.bak`

---

## Milestone 1 — Fix #1: Replace `wmic` in `launch.py`
- [x] Edit `launch.py` → replace `_pids_by_cmdline()` wmic call with PowerShell `Get-CimInstance`
- [x] Add `logger.warning(...)` on exception (not bare `pass`)
- [x] `py_compile launch.py` — passes with no errors
- [x] Manual test: run with Roamin already running → stale instance detected and killed
- [x] Commit: `fix(launch): replace deprecated wmic with Get-CimInstance Win32_Process (#1)`

---

## Milestone 2 — Fix #51: Inject `store` on chat path ⚠️ RESTART REQUIRED
- [x] Edit `agent/core/chat_engine.py` → inject `MemoryStore()` into `loop.registry.store` in `_get_chat_loop()`
- [x] Edit `agent/core/tool_registry.py` → change `store=None` branch from warn+approve to BLOCK with `approval_unavailable` error
- [x] `py_compile agent/core/chat_engine.py agent/core/tool_registry.py`
- [x] ✅ `pytest tests/test_approval_gates.py -v` — existing tests still green
- [x] ⚠️ Restart Roamin
- [x] Manual test: send a chat message asking Roamin to run Python code → approval toast appears
- [x] Commit: `fix(security): block HIGH-risk tools on chat path when approval store unavailable (#51)`

---

## Milestone 3 — Fix #52 + #53: Harden ToolRegistry defaults ⚠️ RESTART REQUIRED
- [x] Edit `agent/core/tool_registry.py` → change unknown-tool branch to deny with `unknown_tool` error
- [x] Edit `agent/core/tool_registry.py` → add module-level `_SKIP_APPROVAL` constant; replace per-call env read
- [x] `py_compile agent/core/tool_registry.py`
- [x] ✅ `pytest tests/test_approval_gates.py -v`
- [x] ⚠️ Restart Roamin
- [x] Commit: `fix(security): deny unknown tools; read ROAMIN_SKIP_APPROVAL once at startup (#52 #53)`

---

## Milestone 4 — Fix #55: Restrict `SAFE_READ_ROOTS` ⚠️ RESTART REQUIRED
- [x] Edit `agent/core/validators.py` → remove `_USER_HOME` from `SAFE_READ_ROOTS`
- [x] Add explicit subdirs: `~/Documents`, `~/Downloads`, `~/Desktop`, `~/AppData/Local/Roamin`
- [x] `py_compile agent/core/validators.py`
- [x] ✅ `pytest tests/test_validators.py -v`
- [x] Add negative test `test_ssh_dir_read_rejected` to `tests/test_validators.py`
- [x] ✅ `pytest tests/test_validators.py::TestValidatePath::test_ssh_dir_read_rejected -v`
- [x] ⚠️ Restart Roamin
- [x] Monitor `logs/audit.jsonl` for unexpected path rejections after restart
- [x] Commit: `fix(security): restrict SAFE_READ_ROOTS — remove entire home dir (#55)`

---

## Milestone 5 — Fix #54: URL Allowlist in `_fetch_url`
- [x] Edit `agent/core/tools.py` → add `_BLOCKED_URL_PATTERNS` regex constant (loopback + private ranges)
- [x] Add early-return SSRF check in `_fetch_url()` before the `requests.get()` call
- [x] `py_compile agent/core/tools.py`
- [x] ✅ `pytest tests/ -k "fetch_url" -v`
- [x] Manual test: `fetch_url({"url": "http://127.0.0.1:8765/status"})` → permission error returned
- [x] Commit: `fix(security): block SSRF in _fetch_url — deny internal/loopback addresses (#54)`

---

## Milestone 6 — Fix #86 + #87: Harden Control API ⚠️ RESTART REQUIRED
- [x] Edit `agent/control_api.py` → change `@app.get("/approve/{approval_id}")` to `@app.post(...)`
- [x] Edit `agent/control_api.py` → change `@app.get("/deny/{approval_id}")` to `@app.post(...)`
- [x] Edit `agent/control_api.py` → remove `"*"` from `allow_origins`, restrict to localhost origins
- [x] Edit `agent/control_api.py` → redact API key from all log lines (replace value with `***`)
- [x] Check `ui/control-panel/src/` for any `fetch('/approve/...')` or `fetch('/deny/...')` GET calls → update to POST
- [x] `py_compile agent/control_api.py`
- [x] ✅ `pytest tests/test_hitl_approval.py -v` — passes after Milestone 11
- [x] ⚠️ Restart Roamin
- [x] Commit: `fix(security): POST-only approve/deny endpoints; tighten CORS; redact key from logs (#86 #87)`

---

## Milestone 7 — Fix #77: Block Agent Writes to Plugin Directory
- [x] Edit `agent/core/validators.py` → add `_BLOCKED_WRITE_PATHS` list: `agent/plugins/`, `agent/core/`, entry scripts
- [x] Add denylist check in `validate_path()` for `mode == "write"` BEFORE allowlist check
- [x] `py_compile agent/core/validators.py`
- [x] ✅ `pytest tests/test_validators.py -v`
- [x] Add test `test_plugin_dir_write_rejected` to `tests/test_validators.py`
- [x] ✅ `pytest tests/test_validators.py::TestValidatePath::test_plugin_dir_write_rejected -v`
- [x] Manual test: ask Roamin to "create a file in agent/plugins/" → rejected at validator
- [x] Commit: `fix(security): block agent writes to plugin dir and core modules (#77)`

---

## Milestone 8 — Test #100: Add `TestChatPathApprovalBypass`
- [x] Edit `tests/test_approval_gates.py` → add `TestChatPathApprovalBypass` class (3 tests per proposal.md)
- [x] ✅ `pytest tests/test_approval_gates.py::TestChatPathApprovalBypass -v` — all 3 pass
- [x] ✅ `pytest tests/test_approval_gates.py -v` — full file green
- [x] Commit: `test(security): add chat-path approval bypass regression tests (#100)`

---

## Milestone 9 — Test #101: Add Unknown Tool Denial Test
- [x] Edit `tests/test_approval_gates.py` → add `TestUnknownToolDenial` class (2 tests)
- [x] ✅ `pytest tests/test_approval_gates.py::TestUnknownToolDenial -v`
- [x] Commit: `test(security): verify unknown tool execution is denied (#101)`

---

## Milestone 10 — Test #105: Add Auth + CSRF Tests to `test_control_api.py`
- [x] Edit `tests/test_control_api.py` → add `TestAuthRequired` class (3 tests)
- [x] Edit `tests/test_control_api.py` → add `TestApprovalEndpointVerb` class (4 tests)
- [x] ✅ `pytest tests/test_control_api.py::TestAuthRequired -v` — all green
- [x] ✅ `pytest tests/test_control_api.py::TestApprovalEndpointVerb -v` — all green
- [x] Commit: `test(security): add API auth and CSRF endpoint verb tests (#105)`

---

## Milestone 11 — Test #107: Update `test_hitl_approval.py` for POST Endpoints
- [x] Edit `tests/test_hitl_approval.py` → change `client.get(f"/deny/{aid}")` to `client.post(...)`
- [x] Edit `tests/test_hitl_approval.py` → change `client.get(f"/approve/{aid}")` to `client.post(...)`
- [x] Remove dead `_client_with_store()` generator method (never called)
- [x] ✅ `pytest tests/test_hitl_approval.py -v` — all green
- [x] Commit: `test(security): update approval endpoint tests to use POST after #86 fix (#107)`

---

## Final Validation
- [x] ✅ Full security test suite: `pytest tests/test_approval_gates.py tests/test_control_api.py tests/test_hitl_approval.py tests/test_validators.py -v`
- [x] All 61 tests green
- [x] ⚠️ Final Roamin restart with all changes applied
- [x] Update `openspec/changes/v13-security-remediation/.openspec.yaml` → `status: complete`
- [x] Update `openspec/changes/v12-code-triage-audit/tasks.md` → check off "Follow-up openspec created"
- [x] Commit: `chore: mark v13-security-remediation complete`
