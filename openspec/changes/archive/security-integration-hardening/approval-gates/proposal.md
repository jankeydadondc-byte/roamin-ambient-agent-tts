# Proposal: Approval Gates for High-Risk Tools (Priority 7, Task 7.3)

## Why

The agent currently has full system access via tools that can execute arbitrary code, modify files,
and write scripts. Even with path validation and audit logging in place, there's no **human-in-the-loop**
for high-risk operations. This creates three concrete risks:

1. **Accidental Damage** — The LLM could inadvertently delete critical files (`delete_file`),
   run malicious scripts (`run_python`, `run_powershell`, `run_cmd`), or write to wrong locations,
   without any confirmation step before execution.

2. **No Accountability** — Audit logs record what happened, but if a user asks "did I approve that?"
   there's no easy way to know. Was the script run automatically? Or did I say "approve" last time?

3. **Security Boundary Leakage** — Even local-only tools can leak sensitive information if they
   operate without oversight. Path validation prevents writing to wrong places, but it doesn't
   prevent the LLM from asking "where can I write?" and getting a harmful answer back.

The existing HITL approval mechanism (from Priority 6) is **already built**: `pending_approvals`
SQLite table, winotify toast with Approve/Deny buttons, `/approve` and `/deny` Control API endpoints,
and `_handle_blocked_steps()` polling flow. This proposal wires high-risk tool execution through
that existing mechanism.

## What Changes

- **High-Risk Tool Classification** — Add `risk` field to tool registration (HIGH/MED/LOW).
  Tools like `run_python`, `run_powershell`, `run_cmd`, and `delete_file` are HIGH risk.

- **Pre-Execution Approval Gate** — Before executing HIGH-risk tools:
  - Check if approval was pre-granted or already blocked
  - If not approved, create `pending_approval` entry with tool name, action description, params summary
  - Fire winotify toast notification with Approve/Deny buttons
  - Block execution until user approves, denies, or timeout (60s default)
  - Return structured error on denial or timeout

- **Skip Approval Mode** — Add `ROAMIN_SKIP_APPROVAL=1` env var for development/testing bypass. Never skip in production.

## Out of Scope

Items that would require separate work:

- **Real-time UI feedback** — The toast system and winnotify provide sufficient feedback for
  local agent use. Real-time terminal output or live progress updates are not needed.

- **Batch approvals** — Approving multiple tools in one action (e.g., "approve all HIGH risk"
  button) could lead to cascading damage. Better safe than sorry: approve per-operation.

## Impact

**Files modified:**
- `agent/core/tools.py` — Add `risk` and `approval_required` fields to tool registrations
- `agent/core/tool_registry.py` — Pre-execution approval hook in `ToolRegistry.__call__()`

**New files:**
- `tests/test_approval_gates.py` — Comprehensive tests for approval gate behavior

**No new dependencies.** Reuses **entirely** existing Priority 6 HITL infrastructure:
- `pending_approvals` SQLite table (already created)
- `_notify_approval_toast()` winnotify function (already wired)
- `/approve/{id}` and `/deny/{id}` Control API endpoints (already running)
- `wake_listener._handle_blocked_steps()` polling loop (already functional)

**No breaking changes** to tool behavior for LOW/MED risk tools. HIGH-risk tools simply
wait for approval instead of executing immediately. The agent remains responsive during the
approval wait (toast can be dismissed without execution).

## Security Boundary

This is a **local-first, personal-use agent** running on Windows 10/11 with no internet
(except `web_search` tool which is optional). The security model matches this:

- Prevent accidental damage via approval gates
- Provide audit trail for compliance review
- Enable manual oversight without enterprise complexity

Think "seatbelt" not "armored vehicle": the agent assumes you're building your own car
(locally, on your machine), not driving a public bus. Seatbelts are standard; armored glass
is overkill unless you have specific enterprise requirements.

## Risk Matrix

| Risk Type | Severity (1-5) | Mitigation Strategy |
|-----------|----------------|--------------------|
| Bypassed approval gate | ⚠️⚠️⚠️ | Enforce via `tool_registry.execute()` hook; `ROAMIN_SKIP_APPROVAL=1` documented and opt-in only |
| Toast notification blocked | ⚠️ | Document use of `/approve` endpoint if winotify fails |
| Timeout (60s) too short | ⚠️⚠️ | Configurable via `ROAMIN_APPROVAL_TIMEOUT=120` env var |
