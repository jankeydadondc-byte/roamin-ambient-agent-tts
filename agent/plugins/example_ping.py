"""Example plugin -- adds a 'ping' tool that returns 'pong'.

Proves the plugin outlet works. Rename to _example_ping.py to disable.
"""

from __future__ import annotations

from agent.core.tool_registry import ToolRegistry


class Plugin:
    """Minimal plugin that registers a 'ping' tool."""

    name = "example_ping"

    # Register the ping tool into the agent's tool registry
    def on_load(self, registry: ToolRegistry) -> None:
        registry.register(
            name="ping",
            description="Reply with pong (plugin example)",
            risk="low",
            params={},
            implementation=lambda params: {"success": True, "result": "pong"},
        )

    # Nothing to clean up for this simple plugin
    def on_unload(self) -> None:
        pass
