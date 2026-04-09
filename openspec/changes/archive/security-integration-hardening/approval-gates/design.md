# Design: Approval Gates for High-Risk Tools (Task 7.3)

## Design Decisions

### D1: Wire existing HITL infrastructure, don't build new

**Decision:** Reuse the Priority 6 `pending_approvals` table, toast notifications, and API endpoints
instead of building a separate approval system.

**Why:** All components already exist and are tested:
- `pending_approvals` SQLite table in `memory_store.py` (commit af9b59c)
- `_notify_approval_toast()` with winnotify + Approve/Deny buttons
- `/approve/{id}` and `/deny/{id}` Control API endpoints
- `wake_listener._handle_blocked_steps()` polling loop

The only new work is identifying which tools need approval via a risk field.

### D2: Risk level in tool registration, not runtime discovery

**Decision:** Add `risk` field to tool registration (default LOW). HIGH-risk tools
require approval before execution.

**Why:** Runtime discovery is slow and error-prone. Every tool should declare its own risk level
at definition time.

### D3: Structured errors on denial/timeout

**Decision:** Return structured error dict when approval denied or timeout occurs:
```python
{
    "success": False,
    "error_type": "approval_denied",  # or "approval_timeout"
    "message": "run_python execution blocked: user denied approval"
}
```

**Why:** Matches existing tool error format. AgentLoop's `_execute_step()` handles all structured
errors uniformly.

### D4: Toast notifications non-blocking

**Decision:** Approval toast fires and blocks execution, but user can dismiss it without
execution if they want to proceed anyway. Tool execution waits for actual button click.

**Why:** Windows 10/11 toasts have built-in close/dismiss behavior. User agency matters.

### D5: Approval timeout configurable

**Decision:** Default `ROAMIN_APPROVAL_TIMEOUT=60` seconds, configurable via env var. Timeout
returns structured error without executing the tool.

**Why:** Prevents indefinite blocking if user forgets to approve/deny.

### D6: Skip approval mode for development

**Decision:** Add `ROAMIN_SKIP_APPROVAL=1` env var to bypass approval gates entirely. Never enabled in production config.

**Why:** Development workflow needs rapid iteration. Approval gates add ~60s latency per HIGH-risk
tool call, which slows testing. This mode is explicitly documented and opt-in.

## Architecture

```
ToolRegistry.__call__(name="run_python", params=...)
    |
    v
Check tool risk level from registration
    |
    +-- risk == "HIGH"?
        |
        +-- Yes: Call approve_before_execution()
            |
            +-- Create pending_approval entry (store.create_pending_approval)
            +-- Fire toast notification (_notify_approval_toast)
            +-- Poll approval resolution (store.poll_approval_resolution)
                |
                +-- Approved? --> Proceed to registry._execute_impl(name, params)
                +-- Denied/Timeout? --> Return structured error dict
        |
        +-- No: Execute immediately via registry._execute_impl()
    |
    v
Tool implementation executes (with path validation first)
    |
    v
Audit log entry: tool_execution
```

## Implementation Code

### 1. Tool Registration with Risk Level

In `agent/core/tools.py`, each HIGH-risk tool declares its risk level at registration:

```python
class RunPythonTool:
    def on_load(self, registry):
        registry.register_tool(
            name="run_python",
            description="Execute Python code (eval-like operation)",
            implementation=self._execute,
            risk="HIGH",          # <-- Risk level declared here
            approval_required=True,  # <-- Defaults to True for HIGH
        )

class DeleteFileTool:
    def on_load(self, registry):
        registry.register_tool(
            name="delete_file",
            description="Delete a file from filesystem",
            implementation=self._execute,
            risk="HIGH",          # <-- Destructive operation
            approval_required=True,
        )

class WriteFileTool:
    def on_load(self, registry):
        registry.register_tool(
            name="write_file",
            description="Write content to a file",
            implementation=self._execute,
            risk="MEDIUM",        # <-- Path validation is sufficient gate
            approval_required=False,  # No approval needed
        )

class ReadFileTool:
    def on_load(self, registry):
        registry.register_tool(
            name="read_file",
            description="Read file contents",
            implementation=self._execute,
            risk="LOW",           # <-- Read-only operation
            approval_required=False,
        )
```

**Default behavior:** If `risk` field not specified, default to LOW (backward compatible).

### 2. Pre-Execution Approval Hook

Add `approve_before_execution()` function in `agent/core/tool_registry.py`:

```python
from agent.core.memory.memory_store import MemoryStore
from agent.core.screen_observer import _notify_approval_toast

def approve_before_execution(
    registry: ToolRegistry,
    store: MemoryStore,
    tool_name: str,
    params: dict | None,
    timeout: int = 60,
    skip_approval: bool = False,
) -> tuple[bool, dict | None]:
    """
    Request approval before executing HIGH-risk tool.

    Returns:
        (success, result_or_error_dict):
            - If success=True and user approved: proceed to normal execution
            - If denied/timeout/error: return structured error dict
    """

    # Check if skip mode is enabled (dev only)
    if skip_approval:
        _log_skip_warning(f"Bypassing approval gate for {tool_name}")
        return True, None

    # Get tool risk level from registration
    tool_info = registry.get_tool(tool_name)
    if not tool_info or tool_info.risk in ("LOW", "MEDIUM"):
        return True, None  # LOW/MED risk tools skip approval gate

    if tool_info.approval_required is False:
        return True, None  # Explicitly opt-out of approval

    # Build action description from params
    action_desc = f"{tool_name} operation"
    if params:
        param_str = str(params)
        if len(param_str) > 300:
            action_desc += f" ({param_str[:277]}...)"
        else:
            action_desc += f": {param_str}"

    # Create pending approval request
    aid = store.create_pending_approval(
        task_run_id=None,
        step_number=0,
        tool=tool_name,
        action=action_desc,
        params_json=str(params) if params else "",
        risk=tool_info.risk,
    )

    # Fire toast notification (winnotify)
    _notify_approval_toast(
        title=f"Approve {tool_name}",
        message=action_desc,
        aid=aid,
        task_run_id=None,
    )

    # Wait for approval resolution (polling loop)
    result = store.poll_approval_resolution(aid, timeout)

    # Handle resolution
    if result["status"] == "approved":
        # Approved — proceed to normal execution via registry._execute_impl()
        return True, None

    else:  # denied or timeout
        error_msg = f"{tool_name} execution blocked: {result.get('reason', 'user denial or timeout')}"
        return False, {
            "success": False,
            "error_type": f"approval_{result['status']}",
            "message": error_msg,
        }

def _log_skip_warning(tool_name: str):
    """Log skip approval warning to audit trail."""
    from agent.core.audit_log import audit_log
    audit_log.append(
        tool="skip_approval",
        params={"tool_name": tool_name},
        result_summary=f"Approval gate bypassed ({tool_name})",
        duration_ms=1,
        success=False,
    )
```

### 3. Wire Into ToolRegistry.__call__()

Add approval check to the main `execute()` method:

```python
class ToolRegistry:
    def __call__(self, name: str, params: dict | None) -> dict[str, Any]:
        """Execute a tool by name."""

        # Get store via dependency injection (already wired from run_wake_listener.py)
        store = self.store

        # Call pre-execution approval hook
        success, result_or_error = approve_before_execution(
            registry=self,
            store=store,
            tool_name=name,
            params=params,
            timeout=60,  # Can be configured via ROAMIN_APPROVAL_TIMEOUT env var
            skip_approval=os.environ.get("ROAMIN_SKIP_APPROVAL", "").lower() == "1",
        )

        if not success:
            return result_or_error  # Structured error from approval denial/timeout

        # Execute the tool (LOW/MED risk or approved HIGH risk)
        return self._execute_impl(name, params)

    def _execute_impl(self, name: str, params: dict | None) -> dict[str, Any]:
        """Internal execution after approval check passes."""
        if not hasattr(self, "_tools") or name not in self._tools:
            return {
                "success": False,
                "error_type": "tool_not_found",
                "message": f"Tool '{name}' not registered",
            }

        tool = self._tools[name]
        try:
            result = tool(params)
            return {
                "success": True,
                "result": result,
            }
        except Exception as e:
            return {
                "success": False,
                "error_type": "execution_error",
                "message": str(e),
            }
```

## Risk Level Definitions

| Risk | Definition | Examples | Approval Needed |
|------|------------|----------|-----------------|
| **HIGH** | Code execution or destructive operations | `run_python`, `run_powershell`, `run_cmd`, `delete_file` | ✅ Required |
| **MEDIUM** | Data-modifying operations with validation | `write_file`, `move_file`, `clipboard_write` | ⚠️ Validation only (path guards) |
| **LOW** | Read-only, informational, no direct system effects | `read_file`, `web_search`, `memory_recall`, `git_status` | ❌ None |

## Failure Modes

### Toast Notification Fails

If winnotify toast fails to display:

1. Catch exception in `_notify_approval_toast()`
2. Log error to audit trail
3. Return structured error: `{"error_type": "notification_failed"}`
4. AgentLoop retries via fallback chain or marks task as failed

### User Closes Windows Without Clicking

User can dismiss toast without clicking Approve/Deny:

1. Toast disappears after 5s (default winnotify behavior)
2. No execution occurs (user must re-click or wait for timeout)
3. This is acceptable — user explicitly chose not to proceed

### Multiple Approvals Pending

User can have multiple approvals pending at once:

1. `pending_approvals` table handles concurrent rows (SQLite allows this)
2. Toast system stacks notifications (Windows 10/11 native behavior)
3. Each approval has unique ID — user clicks the right button
4. No race conditions — each approval resolution updates its own row

## Testing Strategy

The existing HITL tests will serve as foundation, plus new tests for tool risk classification:

- ✅ `tests/test_hitl_approval.py` — Existing infrastructure tests (reuse)
- ✅ New: High-risk tool execution triggers approval gate
- ✅ New: Medium/low-risk tools execute immediately (no gate)
- ✅ New: Approval timeout returns structured error
- ✅ New: Skip approval mode bypasses gate when env var set
