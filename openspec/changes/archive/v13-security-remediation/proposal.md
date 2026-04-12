# v13 Security Remediation — Implementation Plan

> **Source:** v12 Code Triage Audit (openspec/changes/v12-code-triage-audit/)
> **Scope:** 4 P1 findings + 9 security-critical P2 findings = 13 total
> **Execution order:** Dependency-sorted — each fix is safe to apply with no forward dependencies.
> **⚠️ Roamin restart required** after Milestones 2, 3, 4 (runtime changes). Tests run after each milestone.

---

## 🎯 Goal

Eliminate all P1 security vulnerabilities and the highest-impact P2 security gaps identified in
the v12 triage. After this openspec is complete:

- No HIGH-risk tool can execute without user approval on any code path
- The plugin directory cannot be written to by the agent without approval
- The approval API cannot be triggered by cross-site image tags (CSRF)
- Sensitive paths (`.ssh`, `.aws`) are outside the read allowlist
- Credential material is never emitted to logs
- Unknown tool names are denied, not silently approved
- All security invariants have regression tests

---

## 🔧 Architecture Impact

| File | Change Type | Breaking? |
|---|---|---|
| `launch.py` | Replace `wmic` subprocess | No — same external behavior |
| `agent/core/tool_registry.py` | Deny unknown tools; fix env-var timing | No |
| `agent/core/chat_engine.py` | Inject `store` into chat-path registry | No |
| `agent/core/tools.py` | Add URL allowlist to `_fetch_url` | ⚠️ Breaks fetching localhost |
| `agent/core/validators.py` | Restrict `SAFE_READ_ROOTS` | ⚠️ Breaks reading arbitrary `~/` paths |
| `agent/control_api.py` | Change approve/deny to POST; tighten CORS; redact log | ⚠️ UI must switch to POST |
| `tests/test_approval_gates.py` | Add `TestChatPathApprovalBypass` class | No |
| `tests/test_approval_gates.py` | Add unknown-tool denial test | No |
| `tests/test_control_api.py` | Add auth + CSRF verb tests | No |
| `tests/test_hitl_approval.py` | Update approve/deny calls to POST | No |

---

## 📋 Milestone Breakdown

---

### Milestone 1 — Fix #1: Replace `wmic` in `launch.py`

**Finding:** #1 | **Risk:** ⚠️ P1 — stale processes spawn silently on Win11 22H2+
**File:** `launch.py`
**Function:** `_pids_by_cmdline()`

#### What to change

Replace the `wmic process get ...` subprocess call with an equivalent PowerShell
`Get-CimInstance Win32_Process` call. Add a logged warning (not a silent `pass`) if
the fallback also fails.

**Current code (lines 72–96):**
```python
result = subprocess.run(
    ["wmic", "process", "get", "ProcessId,CommandLine", "/FORMAT:CSV"],
    capture_output=True, text=True,
)
for line in result.stdout.splitlines():
    ...
```

**Replace with:**
```python
# Query processes via CIM — wmic removed from Win11 22H2+
try:
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine "
            "| ConvertTo-Csv -NoTypeInformation",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    for line in result.stdout.splitlines():
        line = line.strip().strip('"')
        if not line or line.startswith("ProcessId"):
            continue
        for pattern in patterns:
            if pattern.lower() in line.lower():
                # CSV: "ProcessId","CommandLine"
                parts = line.split('","', 1)
                if parts:
                    try:
                        pid = int(parts[0].strip('"'))
                        if pid > 0:
                            found[pid] = pattern
                    except ValueError:
                        pass
                break
except Exception as e:
    logger.warning("[Launcher] Process scan failed (layer 4 disabled): %s", e)
```

#### Expected outcome
- Stale wake listener processes correctly detected on Windows 11 22H2+
- Failure is logged, not silently swallowed

#### Verification
```
# Manual: run launch.py with Roamin already running — verify it detects and kills the stale process
python launch.py

# Static check
py_compile launch.py
flake8 launch.py --max-line-length=120
```

#### ⚠️ Risk Assessment
- **Breaking Change:** None — same behavior on supported systems; adds detection on Win11 22H2+
- **Rollback:** `git revert` the commit; or restore from `.bak`

---

### Milestone 2 — Fix #51: Inject `store` on the chat path

**Finding:** #51 | **Risk:** ⚠️⚠️⚠️⚠️ P1 ESCALATION — ALL HIGH-risk tools bypass approval on chat path
**Files:** `agent/core/chat_engine.py`, `agent/core/tool_registry.py`

#### What to change

**Root cause:** `ToolRegistry.execute()` calls `getattr(self, "store", None)`. The `store`
attribute is only injected in `run_wake_listener.py` (voice path). The chat path
(`chat_engine.py` → `AgentLoop`) never injects `store`, so it is always `None` →
`approve_before_execution()` warns and returns `True, None` → tool runs without approval.

**Fix strategy:** Inject a real `MemoryStore` into the chat-path registry at creation time in
`_get_chat_loop()`. This is the minimal change with the smallest blast radius.

**In `agent/core/chat_engine.py`, inside `_get_chat_loop()` after `load_plugins`:**

```python
# Inject approval store into chat-path registry (mirrors voice path wiring)
try:
    from agent.core.memory.memory_store import MemoryStore
    loop.registry.store = MemoryStore()
    logger.info("[chat_engine] Approval store injected into chat registry")
except Exception as exc:
    logger.warning("[chat_engine] Could not inject approval store — HIGH-risk tools will be blocked: %s", exc)
```

**In `agent/core/tool_registry.py`, `approve_before_execution()` — change the store=None branch:**

```python
# No store available — BLOCK execution, do not silently approve
if store is None:
    logger.error(
        "Approval store not injected; HIGH-risk tool '%s' BLOCKED (chat path wiring missing)",
        tool_name,
    )
    return False, {
        "success": False,
        "error_type": "approval_unavailable",
        "message": f"Cannot execute '{tool_name}': approval store not available. "
                   "This is a configuration error — HIGH-risk tools require an approval store.",
    }
```

#### Expected outcome
- Chat-path HIGH-risk tool calls block until user approves via Control Panel
- If store injection fails at startup, the tool is DENIED (not silently approved)
- Voice path behavior unchanged

#### Verification
```
pytest tests/test_approval_gates.py -v
# Specifically: TestChatPathApprovalBypass (added in Milestone 8)
```

#### ⚠️ Risk Assessment
- **Breaking Change:** ⚠️⚠️ Chat-path HIGH-risk tools (run_python, write_file, etc.) now BLOCK
  instead of running silently. This is the correct behavior but changes runtime UX.
- **Restart required:** Yes — `chat_engine.py` holds a module-level singleton (`_chat_loop`)
- **Rollback:** `git revert`; or temporarily re-set the store=None branch back to `return True, None`
  while the UI approval flow is validated

---

### Milestone 3 — Fix #52 + #53: Harden `ToolRegistry` defaults

**Findings:** #52 (unknown tool assumed safe), #53 (ROAMIN_SKIP_APPROVAL re-read per call)
**File:** `agent/core/tool_registry.py`

#### Fix #52 — Deny unknown tools

**In `approve_before_execution()`, change the "unknown tool" branch:**

```python
# Current (unsafe):
if not tool_info:
    return True, None  # Unknown tool — assume safe

# Replace with:
if not tool_info:
    logger.warning("Approval gate: unknown tool '%s' — DENIED (not in registry)", tool_name)
    return False, {
        "success": False,
        "error_type": "unknown_tool",
        "message": f"Tool '{tool_name}' is not registered. Unknown tools are denied by default.",
    }
```

#### Fix #53 — Read skip flag once at startup

**At module level in `tool_registry.py`**, add:

```python
# Read skip flag once at import time — mutable env var re-reads are a security gap
_SKIP_APPROVAL: bool = os.environ.get("ROAMIN_SKIP_APPROVAL", "").lower() == "1"
```

**In `ToolRegistry.execute()`**, replace:
```python
# Current:
skip_approval=os.environ.get("ROAMIN_SKIP_APPROVAL", "").lower() == "1",

# Replace with:
skip_approval=_SKIP_APPROVAL,
```

#### Expected outcome
- Unregistered tool names return a structured denial error
- `ROAMIN_SKIP_APPROVAL` cannot be injected at runtime after agent startup

#### Verification
```
pytest tests/test_approval_gates.py -v
# Specifically: test for unknown tool denial (added in Milestone 9)
py_compile agent/core/tool_registry.py
```

#### ⚠️ Risk Assessment
- **Breaking Change:** None for normal operation — unknown tools were never intended to succeed
- **Restart required:** Yes (module-level constant)

---

### Milestone 4 — Fix #55: Restrict `SAFE_READ_ROOTS`

**Finding:** #55 | **Risk:** ⚠️⚠️ P2 — model can read `~/.ssh/id_rsa`, `~/.aws/credentials`
**File:** `agent/core/validators.py`

#### What to change

Remove `_USER_HOME` from `SAFE_READ_ROOTS`. Replace with explicit subdirectories that
cover legitimate use cases (Documents, Downloads, Desktop, AppData/Local for config reads):

```python
# Directories where read operations are allowed (explicit — NOT entire home dir)
SAFE_READ_ROOTS: list[Path] = [
    _PROJECT_ROOT,
    _USER_HOME / "Documents",
    _USER_HOME / "Downloads",
    _USER_HOME / "Desktop",
    _USER_HOME / "AppData" / "Local" / "Roamin",  # Roamin-specific config
    _TEMP_DIR,
]
```

#### Expected outcome
- `~/.ssh/id_rsa`, `~/.aws/credentials`, `~/.gitconfig` are outside read roots → rejected
- `~/Documents/notes.txt` still readable
- Test `test_user_home_read_accepted` in `test_validators.py` will need updating to use `~/Documents`

#### Verification
```
pytest tests/test_validators.py -v
py_compile agent/core/validators.py
```

#### Update required in test
In `tests/test_validators.py`, `test_user_home_read_accepted`:
```python
# Change from:
path = os.path.join(home, "Documents", "test.txt")
# To — same path, test already correct. But add a new negative test:
def test_ssh_dir_read_rejected(self):
    result = validate_path(str(Path.home() / ".ssh" / "id_rsa"), mode="read")
    assert result is not None
    assert result["success"] is False
```

#### ⚠️ Risk Assessment
- **Breaking Change:** ⚠️⚠️ Any existing tool call that reads a file outside the explicit roots
  (e.g., a file in `~/AppData/Roaming/`) will now be rejected. Monitor logs after restart.
- **Restart required:** Yes
- **Rollback:** Add `_USER_HOME` back to `SAFE_READ_ROOTS` temporarily if a legitimate path breaks

---

### Milestone 5 — Fix #54: URL Allowlist in `_fetch_url`

**Finding:** #54 | **Risk:** ⚠️⚠️ P2 — SSRF: model can call `127.0.0.1:1234` (LM Studio) or `127.0.0.1:8765` (Control API)
**File:** `agent/core/tools.py`
**Function:** `_fetch_url()`

#### What to change

Add a blocked-host check before any outbound request. Internal loopback addresses and
private network ranges must be explicitly blocked:

```python
# Block internal/loopback addresses (SSRF prevention)
_BLOCKED_URL_PATTERNS = re.compile(
    r"^https?://(localhost|127\.|0\.0\.0\.0|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)",
    re.IGNORECASE,
)

def _fetch_url(params: dict) -> dict:
    url = params.get("url", "")
    if not url:
        return _fail("No URL provided", "validation")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return _fail(f"URL must start with http:// or https:// — got: {url[:80]}", "validation")
    # Block SSRF: internal addresses and loopback are never fetchable
    if _BLOCKED_URL_PATTERNS.match(url):
        return _fail(
            f"URL '{url[:80]}' targets an internal address — fetch_url is for external URLs only.",
            "permission",
        )
    # ... rest of existing implementation unchanged
```

#### Expected outcome
- `fetch_url({"url": "http://127.0.0.1:8765/approve/42"})` → rejected with permission error
- `fetch_url({"url": "https://example.com"})` → proceeds normally

#### Verification
```
pytest tests/ -k "fetch_url or test_tool" -v
py_compile agent/core/tools.py
```

#### ⚠️ Risk Assessment
- **Breaking Change:** ⚠️ Any agent workflow that intentionally fetched a localhost URL will break.
  Check `audit_log.jsonl` for any historical `fetch_url` calls to `127.x.x.x` before deploying.
- **Restart required:** No (tools.py is imported, no singleton)

---

### Milestone 6 — Fix #86 + #87: Harden Control API

**Findings:** #86 (CSRF via GET approval), #87 (API key in logs)
**File:** `agent/control_api.py`

#### Fix #86 — Change approve/deny endpoints to POST

**Change `@app.get("/approve/{approval_id}")` → `@app.post("/approve/{approval_id}")`**
**Change `@app.get("/deny/{approval_id}")` → `@app.post("/deny/{approval_id}")`**

Also tighten the CORS middleware — remove the wildcard `"*"` from `allow_origins`:

```python
# Replace:
allow_origins=["http://localhost", "http://127.0.0.1", "*"],

# With:
allow_origins=[
    "http://localhost",
    "http://localhost:5173",   # Vite dev server
    "http://127.0.0.1",
    "http://127.0.0.1:5173",
],
```

#### Fix #87 — Redact API key from logs

**In `websocket_events()`, change the debug log line:**

```python
# Current (leaks key):
logger.warning(f"WebSocket auth failed: expected {key}, got {provided}")

# Replace with:
logger.warning(
    "WebSocket auth failed: expected key len=%d, got=%s",
    len(key),
    "***" if provided else "(none)",
)
```

Apply same redaction to any other location that logs `key` or `provided` directly.

#### Expected outcome
- `<img src="http://127.0.0.1:8765/approve/42">` in a webpage no longer auto-approves a tool
- API key value never appears in log files even with `ROAMIN_DEBUG=1`

#### Verification
```
pytest tests/test_hitl_approval.py -v   # Will FAIL until Milestone 11 updates test calls to POST
pytest tests/test_control_api.py -v     # Will partially fail until Milestone 10

py_compile agent/control_api.py
```

#### ⚠️ UI Impact
**The approval toast buttons in the Control Panel UI that call `/approve/{id}` and `/deny/{id}`
must be updated to use POST method.** Check `ui/control-panel/src/` for any `fetch('/approve/...')`
calls and update them. This is a required follow-on change in the same commit.

#### ⚠️ Risk Assessment
- **Breaking Change:** ⚠️⚠️⚠️ All callers of approve/deny endpoints must switch to POST.
  This includes the toast notification buttons and any test that calls GET on these routes.
- **Restart required:** Yes (control_api.py is the running server)

---

### Milestone 7 — Fix #77: Protect Plugin Directory from Write Access

**Finding:** #77 | **Risk:** ⚠️⚠️⚠️⚠️ P1 — write_file to `agent/plugins/` → persistent code injection on restart
**File:** `agent/core/validators.py`

#### What to change

Add an explicit write-protect rule for the plugin directory. Even though `agent/plugins/` is
inside `_PROJECT_ROOT` (which is in `SAFE_WRITE_ROOTS`), it must be blocked for agent-initiated
writes. The correct mechanism is a `BLOCKED_WRITE_PATHS` denylist checked _before_ the
allowlist pass:

```python
# Paths that must never be agent-writable, even though inside SAFE_WRITE_ROOTS
_PLUGIN_DIR = _PROJECT_ROOT / "agent" / "plugins"
_BLOCKED_WRITE_PATHS: list[Path] = [
    _PLUGIN_DIR,
    _PROJECT_ROOT / "agent" / "core",    # core modules also protected
    _PROJECT_ROOT / "run_wake_listener.py",
    _PROJECT_ROOT / "launch.py",
]

def validate_path(path: str, mode: str = "read") -> dict | None:
    ...
    # After resolving path, before allowlist check:
    if mode == "write":
        for blocked in _BLOCKED_WRITE_PATHS:
            try:
                resolved.relative_to(blocked.resolve())
                return {
                    "success": False,
                    "error": f"Path '{resolved}' is a protected system directory — agent writes are not allowed here.",
                    "category": "permission",
                }
            except ValueError:
                continue
    ...
```

#### Expected outcome
- `write_file({"path": "agent/plugins/evil.py", "content": "..."})` → rejected with permission error
- `write_file({"path": "workspace/output.txt", "content": "..."})` → proceeds normally

#### Verification
```
pytest tests/test_validators.py -v
py_compile agent/core/validators.py
```

#### ⚠️ Risk Assessment
- **Breaking Change:** ⚠️ Any legitimate write to `agent/core/` or `agent/plugins/` via the
  agent (e.g., plugin self-update) will now be blocked. This is intentional — such writes
  should go through a dedicated install API, not the general-purpose file tool.
- **Restart required:** No (validators.py has no singleton state)

---

### Milestone 8 — Test Fix #100: Add `TestChatPathApprovalBypass`

**Finding:** #100 | **Risk:** P1 — no regression coverage for the most critical security fix
**File:** `tests/test_approval_gates.py`

#### What to add

Add a new test class after `TestBuiltinHighRiskTools`:

```python
class TestChatPathApprovalBypass:
    """Verify chat path (store=None) blocks HIGH-risk tools — finding #51 regression."""

    def test_no_store_blocks_high_risk_tool(self):
        """HIGH-risk tool on store-less registry returns approval_unavailable error."""
        reg = ToolRegistry()
        # Explicitly do NOT inject reg.store — mirrors chat path before fix
        impl = MagicMock(return_value={"success": True, "result": "ran"})
        reg.register("_test_high_chat", "Test", "high", {"code": "str"}, impl)

        result = reg.execute("_test_high_chat", {"code": "print('hi')"})

        assert result["success"] is False
        assert result["error_type"] == "approval_unavailable"
        impl.assert_not_called()

    def test_no_store_allows_low_risk_tool(self):
        """LOW-risk tools on store-less registry still execute normally."""
        reg = ToolRegistry()
        impl = MagicMock(return_value={"success": True, "result": "read_ok"})
        reg.register("_test_low_chat", "Test", "low", {"path": "str"}, impl)

        result = reg.execute("_test_low_chat", {"path": "test.txt"})

        assert result["success"] is True
        impl.assert_called_once()

    def test_store_injection_enables_approval_flow(self, mock_toast):
        """After store injection (like chat_engine does it), approval flow activates."""
        reg = ToolRegistry()
        reg.store = MagicMock()
        reg.store.create_pending_approval.return_value = 99
        reg.store.poll_approval_resolution.return_value = {"status": "approved", "reason": ""}

        impl = MagicMock(return_value={"success": True, "result": "ran"})
        reg.register("_test_high_injected", "Test", "high", {"code": "str"}, impl)

        result = reg.execute("_test_high_injected", {"code": "1+1"})

        assert result["success"] is True
        reg.store.create_pending_approval.assert_called_once()
```

#### Verification
```
pytest tests/test_approval_gates.py::TestChatPathApprovalBypass -v
```

---

### Milestone 9 — Test Fix #101: Add Unknown Tool Denial Test

**Finding:** #101 | **Risk:** P2 — unknown tool silently approved; now fixed but untested
**File:** `tests/test_approval_gates.py`

#### What to add

Add to `TestRiskLevelRouting`:

```python
def test_unknown_tool_denied(self, registry, mock_toast):
    """Unregistered tool name must return denial, not silent success."""
    result = registry.execute("definitely_not_a_real_tool_xyz", {})

    assert result["success"] is False
    assert result["error_type"] == "unknown_tool"
    mock_toast.assert_not_called()
```

#### Verification
```
pytest tests/test_approval_gates.py::TestRiskLevelRouting::test_unknown_tool_denied -v
```

---

### Milestone 10 — Test Fix #105: Add Auth + CSRF Verb Tests to `test_control_api.py`

**Finding:** #105 | **Risk:** P2 — no auth or CSRF coverage in control API tests
**File:** `tests/test_control_api.py`

#### What to add

```python
import os
from unittest.mock import patch


class TestAuthRequired:
    """Verify API key middleware rejects unauthenticated requests."""

    def test_protected_endpoint_requires_api_key(self):
        """With ROAMIN_CONTROL_API_KEY set, missing key returns 401."""
        with patch.dict(os.environ, {"ROAMIN_CONTROL_API_KEY": "test-secret-key"}):
            with TestClient(app) as client:
                r = client.get("/status")
                # No key provided — must be 401
                assert r.status_code == 401

    def test_correct_api_key_is_accepted(self):
        """Correct x-roamin-api-key header passes authentication."""
        with patch.dict(os.environ, {"ROAMIN_CONTROL_API_KEY": "test-secret-key"}):
            with TestClient(app) as client:
                r = client.get("/status", headers={"x-roamin-api-key": "test-secret-key"})
                assert r.status_code == 200

    def test_wrong_api_key_is_rejected(self):
        """Wrong key value returns 401."""
        with patch.dict(os.environ, {"ROAMIN_CONTROL_API_KEY": "test-secret-key"}):
            with TestClient(app) as client:
                r = client.get("/status", headers={"x-roamin-api-key": "wrong-key"})
                assert r.status_code == 401


class TestApprovalEndpointVerb:
    """Verify approve/deny endpoints require POST and reject GET — finding #86 regression."""

    def test_approve_get_returns_405(self):
        """GET /approve/{id} must return 405 Method Not Allowed after fix."""
        with TestClient(app) as client:
            r = client.get("/approve/1")
            assert r.status_code == 405

    def test_deny_get_returns_405(self):
        """GET /deny/{id} must return 405 Method Not Allowed after fix."""
        with TestClient(app) as client:
            r = client.get("/deny/1")
            assert r.status_code == 405

    def test_approve_post_succeeds(self):
        """POST /approve/{id} is the correct verb and must be accepted (404 for missing ID is OK)."""
        with TestClient(app) as client:
            r = client.post("/approve/9999")
            # 404 is correct (approval not found); 405 would mean wrong verb — that's a failure
            assert r.status_code != 405
```

#### Verification
```
pytest tests/test_control_api.py::TestAuthRequired -v
pytest tests/test_control_api.py::TestApprovalEndpointVerb -v
```

---

### Milestone 11 — Test Fix #107: Update `test_hitl_approval.py` for POST Endpoints

**Finding:** #107 | **Risk:** P2 — tests confirm CSRF-vulnerable GET behavior
**File:** `tests/test_hitl_approval.py`
**Dependency:** Must run AFTER Milestone 6 (control_api.py POST fix is applied)

#### What to change

In `TestApprovalAPIEndpoints`:

```python
# Change:
resp = client.get(f"/deny/{aid}")
# To:
resp = client.post(f"/deny/{aid}")

# Change:
resp = client.get(f"/approve/{aid}")
# To:
resp = client.post(f"/approve/{aid}")
```

Also remove the dead `_client_with_store()` generator method (never called, not decorated
with `@contextmanager`).

#### Verification
```
pytest tests/test_hitl_approval.py::TestApprovalAPIEndpoints -v
```

---

## 📋 Execution Order Summary

| Order | Milestone | Finding | File | Restart? |
|---|---|---|---|---|
| 1 | wmic → PowerShell | #1 | `launch.py` | No |
| 2 | Inject store on chat path | #51 | `chat_engine.py` + `tool_registry.py` | **Yes** |
| 3 | Deny unknown tools + fix env timing | #52, #53 | `tool_registry.py` | **Yes** |
| 4 | Restrict SAFE_READ_ROOTS | #55 | `validators.py` | **Yes** |
| 5 | URL allowlist in fetch_url | #54 | `tools.py` | No |
| 6 | POST approve/deny + CORS + log redact | #86, #87 | `control_api.py` | **Yes** |
| 7 | Block agent writes to plugin dir | #77 | `validators.py` | No |
| 8 | Test: chat path blocks HIGH-risk | #100 | `test_approval_gates.py` | No |
| 9 | Test: unknown tool denied | #101 | `test_approval_gates.py` | No |
| 10 | Test: auth + CSRF verb tests | #105 | `test_control_api.py` | No |
| 11 | Test: update approve/deny to POST | #107 | `test_hitl_approval.py` | No |

---

## 🧪 Full Test Run Command

After all milestones complete, run the full security test suite:

```
pytest tests/test_approval_gates.py tests/test_control_api.py tests/test_hitl_approval.py tests/test_validators.py -v
```

Expected: **all green**.

---

## 🛡️ Rollback Strategy

If any milestone causes unexpected breakage:

```
git log --oneline -15          # find the commit to revert
git revert <commit-hash>       # creates a new revert commit (safe)
```

Each milestone should be its own commit so rollback is surgical. Do NOT squash all 11
milestones into one commit — keep them separable.

---

## 📊 Post-Remediation Security Posture

| Surface | Before v13 | After v13 |
|---|---|---|
| Chat-path HIGH-risk tools | ✗ Bypass — all run without approval | ✅ Blocked until user approves |
| Unknown tool names | ✗ Silently approved | ✅ Denied with error |
| Plugin directory writes | ✗ Agent can inject persistent code | ✅ Blocked at validator layer |
| Approval CSRF (GET) | ✗ `<img src>` triggers approval | ✅ POST-only, CORS restricted |
| Home dir read access | ✗ Full `~/` readable (incl. `.ssh`) | ✅ Only `~/Documents`, `~/Downloads`, `~/Desktop` |
| localhost SSRF | ✗ Agent can call LM Studio/Control API | ✅ Internal addresses blocked |
| API key in logs | ✗ Key value logged in DEBUG mode | ✅ Redacted to `***` |
| Stale process detection (Win11) | ✗ Silent failure on Win11 22H2+ | ✅ PowerShell CIM fallback |
