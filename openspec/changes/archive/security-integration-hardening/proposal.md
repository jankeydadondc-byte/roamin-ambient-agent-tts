# Proposal: Security & Integration Hardening (Priority 7)

## Why

Phases 1-6 delivered a working, stable, feature-complete ambient agent. Every tool works,
the voice pipeline is solid, the Control Panel shows real-time state. But the agent runs
with full system access and zero guardrails on what the LLM can do with that access.

Three concrete risks exist today:

1. **Path traversal** -- `write_file`, `delete_file`, `move_file` accept any absolute path.
   The LLM could write to `C:\Windows\System32` or delete `.git/`. No validation exists
   beyond the 10KB size limit.

2. **Unaudited execution** -- `run_python`, `run_powershell`, `run_cmd` execute arbitrary
   code with the agent's full privileges. Length limits exist (10KB) but there's no record
   of WHAT was executed, no approval gate, and no way to review after the fact.

3. **No secrets discipline** -- API keys for future integrations (web APIs, cloud services)
   have no centralized loading pattern. The one key today (`ROAMIN_CONTROL_API_KEY`) is
   handled correctly via env var, but there's no reusable pattern for the next 5 keys.

This is a personal-use, local-only agent -- not an enterprise product. The security model
should match: **prevent the LLM from doing accidental damage**, not defend against
sophisticated attackers. Think "seatbelt", not "armored vehicle".

## What Changes

- **Path validation** -- New `agent/core/validators.py` module with `validate_path()` that
  constrains file operations to an allowlist of safe directories (project root, home dirs,
  temp). Applied to `write_file`, `delete_file`, `move_file`, `read_file`, `glob_files`,
  `grep_files`.

- **Approval gates for high-risk tools** -- Wire the existing `pending_approvals` mechanism
  (already built in Priority 6 HITL flow) into tool execution. `run_python`, `run_powershell`,
  `run_cmd`, `delete_file` require approval before execution. Approval can come from toast
  button or Control Panel UI.

- **Audit log** -- New `agent/core/audit_log.py` module. Logs every tool execution (tool name,
  params, result summary, duration, timestamp) to `logs/audit.jsonl`. Query via
  `GET /audit-log` endpoint. Simple append-only JSONL, no database.

- **Secrets loader** -- New `agent/core/secrets.py` module. Centralized `.env` + env var
  loading with `get_secret(name)` accessor. Validates required secrets at startup, warns
  on missing optional ones. Uses `python-dotenv` (already common pattern, MIT, pure Python).

- **Response size limit** -- Cap HTTP responses from model endpoints at 256KB to prevent
  memory exhaustion from malformed/runaway responses.

## Out of Scope

Items listed under Priority 7 in CONSOLIDATED_PRIORITIES.md that are NOT security work:

- **7.2 LLM Proxy Layer** -- This is an architecture refactor (normalize multi-provider
  responses). Retagged to Priority 8 (Performance & Architecture).
- **7.3 Browser Automation** -- This is a new feature (Selenium/Playwright). Retagged to
  Priority 9 (New Capabilities).

These are valid work items but don't belong in a security-focused phase.

## Impact

**Files modified:**
- `agent/core/tools.py` -- Apply path validation to file tools, wire approval gates
- `agent/core/tool_registry.py` -- Add pre-execution hook for approval check
- `agent/control_api.py` -- Add `/audit-log` endpoint
- `agent/core/model_router.py` -- Add response size limit

**New files:**
- `agent/core/validators.py` -- Path validation, command validation
- `agent/core/audit_log.py` -- JSONL append-only audit trail
- `agent/core/secrets.py` -- Centralized secrets loader
- `tests/test_validators.py` -- Path validation tests
- `tests/test_audit_log.py` -- Audit logging tests
- `tests/test_secrets.py` -- Secrets loader tests

**New dependency:** `python-dotenv>=1.0.0` (pure Python, MIT, widely used)

**No breaking changes** to any existing tool behavior. Path validation rejects unsafe paths
with a structured error (same format as existing validation errors). Approval gates are
opt-in via tool risk level (already defined in tool_registry).
