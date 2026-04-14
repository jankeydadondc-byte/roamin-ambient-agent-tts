"""Tool registry — catalog of available tools with schemas and implementations."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable

from agent.core import audit_log
from agent.core.tools import TOOL_IMPLEMENTATIONS

logger = logging.getLogger(__name__)

# Read skip flag once at import time — prevents runtime env-var injection attacks
_SKIP_APPROVAL: bool = os.environ.get("ROAMIN_SKIP_APPROVAL", "").lower() == "1"

# Fallback chains: if the primary tool fails, try each entry in order.
# Each entry is (fallback_tool_name, param_adapter | None).
# param_adapter: callable(original_params) -> adapted_params, or None to pass params unchanged.
_TOOL_FALLBACKS: dict[str, list[tuple[str, object]]] = {
    "web_search": [
        ("fetch_url", lambda p: {"url": "https://duckduckgo.com/?q=" + str(p.get("query", ""))}),
    ],
    "memory_recall": [
        ("memory_search", lambda p: {"query": p.get("fact_name", "")}),
    ],
}


def approve_before_execution(
    registry: "ToolRegistry",
    store,  # injected via dependency — no type annotation to avoid forward-ref issues
    tool_name: str,
    params: dict | None,
    timeout: int = 60,
    skip_approval: bool = False,
) -> tuple[bool, dict | None]:
    """
    Request approval before executing HIGH-risk tool.

    Args:
        registry: ToolRegistry with available tools
        store: MemoryStore with pending_approvals table (injected via dependency)
        tool_name: Name of tool to execute (e.g., "run_python")
        params: Tool parameters (for action description)
        timeout: Max seconds to wait for approval (default 60)
        skip_approval: If True, bypass approval gate entirely

    Returns:
        (success, result_or_error_dict):
            - If success=True and user approved: return None (will fall through to normal execution)
            - If denied/timeout/error: return structured error dict

    Side effects:
        - Fires toast notification (winnotify) with Approve/Deny buttons
        - Logs skip warning to audit trail if bypassed
    """

    # Check if skip mode is enabled (dev only)
    if skip_approval:
        from agent.core import audit_log as audit_module

        audit_module.append(
            tool="skip_approval",
            params={"tool_name": tool_name},
            result_summary="Approval gate bypassed (" + tool_name + ")",
            duration_ms=1,
            success=False,
        )
        return True, None  # Fall through to normal execution

    # Get tool risk level from registration
    tool_info = registry.get(tool_name)
    if not tool_info:
        # Unknown tool — deny; never assume safe
        logger.warning("Approval gate: unknown tool '%s' — DENIED (not in registry)", tool_name)
        return False, {
            "success": False,
            "error_type": "unknown_tool",
            "message": f"Tool '{tool_name}' is not registered. Unknown tools are denied by default.",
        }

    risk = tool_info.get("risk", "low")

    # Only HIGH-risk tools require approval by default
    if risk.lower() != "high":
        return True, None  # LOW/MED risk tools skip approval gate

    # No store available — BLOCK execution; never silently approve HIGH-risk tools
    if store is None:
        logger.error(
            "Approval store not injected; HIGH-risk tool '%s' BLOCKED (wiring missing on this call path)",
            tool_name,
        )
        return False, {
            "success": False,
            "error_type": "approval_unavailable",
            "message": (
                f"Cannot execute '{tool_name}': approval store is not available. "
                "HIGH-risk tools require an approval store to be injected before execution."
            ),
        }

    # Explicit opt-out
    if tool_info.get("approval_required", True) is False:
        return True, None

    # Build action description from params
    action_desc = tool_name + " operation"
    if params:
        param_str = str(params)
        if len(param_str) > 300:
            action_desc += f" ({param_str[:277]}...)"
        else:
            action_desc += f": {param_str}"

    logger.info("Approval gate: HIGH-risk tool '%s' requires approval", tool_name)

    # Create pending approval record
    aid = store.create_pending_approval(
        task_run_id=None,
        step_number=0,
        tool=tool_name,
        action=action_desc,
        params_json=str(params) if params else "",
        risk="high",
    )
    logger.info("Approval gate: pending_approval created (aid=%s) for '%s'", aid, tool_name)

    # Fire toast notification (fire-and-forget, never fatal)
    try:
        import json as _json

        from agent.core import ports as _ports

        _port = _ports.CONTROL_API_DEFAULT_PORT
        try:
            from agent.core import paths as _paths

            _disc = _paths.get_project_root() / ".loom" / "control_api_port.json"
            _port = _json.loads(_disc.read_text()).get("port", _port)
        except Exception:
            pass
        from agent.core.screen_observer import _notify_approval_toast

        _notify_approval_toast(aid, action_desc, tool_name, _port)
        logger.info("Approval gate: notification sent (aid=%s, port=%s)", aid, _port)
    except Exception as _e:
        logger.warning("Approval gate: notification failed for %s (aid=%s): %s", tool_name, aid, _e)

    # Poll for user decision — blocks until approved, denied, or timeout
    logger.info("Approval gate: waiting for resolution (aid=%s, timeout=%ss)", aid, timeout)
    result = store.poll_approval_resolution(aid, timeout)
    logger.info("Approval gate: resolved (aid=%s) → status=%s", aid, result["status"])

    # Handle resolution
    if result["status"] == "approved":
        return True, None  # Approved — fall through to normal execution

    else:  # denied or timeout
        error_msg = tool_name + " execution blocked: " + result.get("reason", "user denial or timeout")
        return False, {
            "success": False,
            "error_type": "approval_" + result["status"],
            "message": error_msg,
        }


class ToolRegistry:
    """Registry of tools available to the agent loop."""

    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the full tool catalog with implementations."""
        defaults = [
            # --- Code Execution (high risk) ---
            {
                "name": "run_python",
                "description": "Execute Python code in venv",
                "risk": "high",
                "params": {"code": "str"},
            },
            {
                "name": "run_powershell",
                "description": "Execute PowerShell command",
                "risk": "high",
                "params": {"command": "str"},
            },
            {"name": "run_cmd", "description": "Execute a shell command", "risk": "high", "params": {"command": "str"}},
            {
                "name": "py_compile_check",
                "description": "Check if a Python file compiles",
                "risk": "medium",
                "params": {"path": "str"},
            },
            # --- File System ---
            {"name": "read_file", "description": "Read a file from disk", "risk": "low", "params": {"path": "str"}},
            {
                "name": "write_file",
                "description": "Write content to a file",
                "risk": "high",
                "params": {"path": "str", "content": "str"},
            },
            {
                "name": "list_directory",
                "description": "List files in a directory",
                "risk": "low",
                "params": {"path": "str"},
            },
            {
                "name": "glob",
                "description": "Find files matching a glob pattern",
                "risk": "low",
                "params": {"pattern": "str", "path": "str"},
            },
            {
                "name": "grep",
                "description": "Search file contents with regex",
                "risk": "low",
                "params": {"pattern": "str", "path": "str"},
            },
            {
                "name": "move_file",
                "description": "Move or rename a file",
                "risk": "high",
                "params": {"src": "str", "dst": "str"},
            },
            {
                "name": "delete_file",
                "description": "Delete a file or directory",
                "risk": "high",
                "params": {"path": "str"},
            },
            {
                "name": "file_info",
                "description": "Get file metadata (size, modified date)",
                "risk": "low",
                "params": {"path": "str"},
            },
            # --- Git (read-only) ---
            {"name": "git_status", "description": "Get git repo status", "risk": "low", "params": {}},
            {
                "name": "git_diff",
                "description": "Get git diff",
                "risk": "low",
                "params": {"path": "str | None"},
            },
            {
                "name": "git_log",
                "description": "Show recent git commits",
                "risk": "low",
                "params": {"n": "int"},
            },
            # --- Memory ---
            {
                "name": "memory_write",
                "description": "Store a fact or observation in memory",
                "risk": "low",
                "params": {"type": "str", "data": "dict"},
            },
            {
                "name": "memory_recall",
                "description": "Recall a named fact from memory",
                "risk": "low",
                "params": {"fact_name": "str"},
            },
            {
                "name": "memory_search",
                "description": "Semantic search across all memories",
                "risk": "low",
                "params": {"query": "str"},
            },
            {
                "name": "memory_recent",
                "description": "Get recent conversation history",
                "risk": "low",
                "params": {"limit": "int"},
            },
            # --- System ---
            {"name": "list_processes", "description": "List running Windows processes", "risk": "low", "params": {}},
            {
                "name": "check_port",
                "description": "Check if a TCP port is open on localhost",
                "risk": "low",
                "params": {"port": "int"},
            },
            # --- Web ---
            {
                "name": "web_search",
                "description": "Search the web via DuckDuckGo",
                "risk": "low",
                "params": {"query": "str"},
            },
            {
                "name": "fetch_url",
                "description": "Fetch content from a URL",
                "risk": "medium",
                "params": {"url": "str"},
            },
            # --- Screen & UI ---
            {
                "name": "take_screenshot",
                "description": "Capture and analyze current screen",
                "risk": "low",
                "params": {},
            },
            {
                "name": "notify",
                "description": "Send a Windows notification to the user",
                "risk": "low",
                "params": {"title": "str", "message": "str"},
            },
            {
                "name": "open_url",
                "description": "Open a URL in the default browser",
                "risk": "low",
                "params": {"url": "str"},
            },
            {
                "name": "clipboard_read",
                "description": "Read text from the clipboard",
                "risk": "low",
                "params": {},
            },
            {
                "name": "clipboard_write",
                "description": "Write text to the clipboard",
                "risk": "medium",
                "params": {"text": "str"},
            },
        ]
        for tool in defaults:
            impl = TOOL_IMPLEMENTATIONS.get(str(tool["name"]))
            if impl:
                tool["implementation"] = impl
            self._tools[tool["name"]] = tool

    def register(
        self, name: str, description: str, risk: str, params: dict, implementation: Callable | None = None
    ) -> None:
        """Register a new tool."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "risk": risk,
            "params": params,
            "implementation": implementation,
        }

    def get(self, name: str) -> dict | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    def low_risk_tools(self) -> list[str]:
        """Return names of tools that can be auto-approved."""
        return [t["name"] for t in self._tools.values() if t.get("risk") == "low"]

    def _execute_single(self, name: str, params: dict) -> dict:
        """Execute one tool with no fallback logic. Identical to the old execute() behaviour."""
        tool = self.get(name)
        if tool is None:
            return {"success": False, "error": f"Unknown tool: {name}"}
        impl = tool.get("implementation")
        if impl is None:
            return {"success": False, "error": f"No implementation for: {name}"}
        try:
            return impl(params)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def execute(self, name: str, params: dict) -> dict:
        """Execute a tool by name, with approval gate for HIGH-risk tools.

        On failure, tries configured fallback chain. Every execution is recorded in the audit log.
        """

        # Check if the tool has been disabled via the settings toggle
        try:
            from agent.core.settings_store import get as _settings_get

            tool_states: dict[str, bool] = _settings_get("tool_states", {})
            if not tool_states.get(name, True):
                logger.info("Tool '%s' is disabled — blocking execution", name)
                return {
                    "success": False,
                    "error_type": "tool_disabled",
                    "error": f"Tool '{name}' is currently disabled. Enable it in the Tools panel.",
                }
        except Exception:
            pass  # settings unavailable — default to enabled

        # Call pre-execution approval hook for HIGH-risk tools
        success, result_or_error = approve_before_execution(
            registry=self,
            store=getattr(self, "store", None),  # injected at runtime from run_wake_listener.py
            tool_name=name,
            params=params,
            timeout=60,  # Can be configured via ROAMIN_APPROVAL_TIMEOUT env var
            skip_approval=_SKIP_APPROVAL,  # read once at import time — not mutable at runtime
        )

        if not success:
            return result_or_error  # Structured error from approval denial/timeout

        # Execute the tool (LOW/MED risk or approved HIGH risk)
        t0 = time.perf_counter()
        result = self._execute_single(name, params)
        elapsed = (time.perf_counter() - t0) * 1000

        if result.get("success"):
            # Log successful primary execution to audit trail
            audit_log.append(
                tool=name,
                params=params,
                success=True,
                result_summary=str(result.get("result", ""))[:200],
                duration_ms=elapsed,
            )
            return result

        # Primary failed â€" try fallback chain
        for fallback_name, adapter in _TOOL_FALLBACKS.get(name, []):
            adapted_params = adapter(params) if adapter is not None else params  # type: ignore[operator]
            t1 = time.perf_counter()
            fb_result = self._execute_single(fallback_name, adapted_params)
            fb_elapsed = (time.perf_counter() - t1) * 1000
            if fb_result.get("success"):
                logger.info("Tool '%s' failed; fallback '%s' succeeded", name, fallback_name)
                fb_result["fallback_used"] = fallback_name
                # Log successful fallback to audit trail
                audit_log.append(
                    tool=f"{name}->{fallback_name}",
                    params=adapted_params,
                    success=True,
                    result_summary=str(fb_result.get("result", ""))[:200],
                    duration_ms=fb_elapsed,
                )
                return fb_result
            logger.debug("Fallback '%s' also failed: %s", fallback_name, fb_result.get("error"))

        # All exhausted â€" log the failure
        total_elapsed = (time.perf_counter() - t0) * 1000
        audit_log.append(
            tool=name,
            params=params,
            success=False,
            result_summary=str(result.get("error", ""))[:200],
            duration_ms=total_elapsed,
        )
        return result  # all fallbacks exhausted â€" return original failure

    def format_for_prompt(self) -> str:
        """Format tool list for inclusion in a model prompt."""
        lines = []
        for t in self._tools.values():
            param_str = ", ".join(f"{k}: {v}" for k, v in t.get("params", {}).items())
            lines.append(f"- {t['name']}({param_str}): {t['description']} [risk: {t.get('risk', '?')}]")
        return "\n".join(lines)
