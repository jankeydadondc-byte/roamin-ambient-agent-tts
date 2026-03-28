"""Tool registry — catalog of available tools with schemas."""

from __future__ import annotations

from collections.abc import Callable


class ToolRegistry:
    """Registry of tools available to the agent loop."""

    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the core tools available in this project."""
        defaults = [
            {"name": "read_file", "description": "Read a file from disk", "risk": "low", "params": {"path": "str"}},
            {
                "name": "write_file",
                "description": "Write content to a file",
                "risk": "medium",
                "params": {"path": "str", "content": "str"},
            },
            {
                "name": "run_python",
                "description": "Execute Python code in venv",
                "risk": "medium",
                "params": {"code": "str"},
            },
            {
                "name": "run_powershell",
                "description": "Execute PowerShell command",
                "risk": "high",
                "params": {"command": "str"},
            },
            {"name": "git_status", "description": "Get git repo status", "risk": "low", "params": {}},
            {"name": "git_diff", "description": "Get git diff", "risk": "low", "params": {"path": "str | None"}},
            {
                "name": "observe_screen",
                "description": "Capture and analyze current screen",
                "risk": "low",
                "params": {},
            },
            {
                "name": "web_search",
                "description": "Search the web via DuckDuckGo",
                "risk": "low",
                "params": {"query": "str"},
            },
            {
                "name": "memory_recall",
                "description": "Recall a named fact from memory",
                "risk": "low",
                "params": {"fact_name": "str"},
            },
            {
                "name": "memory_write",
                "description": "Store a fact or observation in memory",
                "risk": "low",
                "params": {"type": "str", "data": "dict"},
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
        ]
        for tool in defaults:
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

    def format_for_prompt(self) -> str:
        """Format tool list for inclusion in a model prompt."""
        lines = []
        for t in self._tools.values():
            param_str = ", ".join(f"{k}: {v}" for k, v in t.get("params", {}).items())
            lines.append(f"- {t['name']}({param_str}): {t['description']} [risk: {t.get('risk', '?')}]")
        return "\n".join(lines)
