"""Tool registry — catalog of available tools with schemas and implementations."""

from __future__ import annotations

import logging
from collections.abc import Callable

from agent.core.tools import TOOL_IMPLEMENTATIONS

logger = logging.getLogger(__name__)

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
        """Execute a tool by name. On failure, try configured fallback chain if any."""
        result = self._execute_single(name, params)
        if result.get("success"):
            return result

        for fallback_name, adapter in _TOOL_FALLBACKS.get(name, []):
            adapted_params = adapter(params) if adapter is not None else params  # type: ignore[operator]
            fb_result = self._execute_single(fallback_name, adapted_params)
            if fb_result.get("success"):
                logger.info("Tool '%s' failed; fallback '%s' succeeded", name, fallback_name)
                fb_result["fallback_used"] = fallback_name
                return fb_result
            logger.debug("Fallback '%s' also failed: %s", fallback_name, fb_result.get("error"))

        return result  # all fallbacks exhausted — return original failure

    def format_for_prompt(self) -> str:
        """Format tool list for inclusion in a model prompt."""
        lines = []
        for t in self._tools.values():
            param_str = ", ".join(f"{k}: {v}" for k, v in t.get("params", {}).items())
            lines.append(f"- {t['name']}({param_str}): {t['description']} [risk: {t.get('risk', '?')}]")
        return "\n".join(lines)
