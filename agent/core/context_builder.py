"""Context builder — assembles memory + screen + tools into a model prompt."""

from __future__ import annotations

from agent.core.memory import MemoryManager
from agent.core.tool_registry import ToolRegistry


class ContextBuilder:
    """Assembles context for the agent loop from memory, screen, and tools."""

    def __init__(self) -> None:
        self._memory = MemoryManager()
        self._registry = ToolRegistry()

    def build(
        self,
        goal: str,
        screen_observation: dict | None = None,
        max_memory_results: int = 5,
    ) -> str:
        """
        Build a context string for a model prompt.

        Args:
            goal: The user's stated goal
            screen_observation: Optional result dict from ScreenObserver.observe()
            max_memory_results: Max recent memory entries to include

        Returns:
            Formatted context string ready to inject into a system or user prompt
        """
        parts: list[str] = []

        parts.append(f"## Goal\n{goal}")

        # Memory context
        recent = self._memory.get_recent_conversations(limit=max_memory_results)
        if recent:
            parts.append("## Recent Context (from memory)")
            for entry in recent[:max_memory_results]:
                content = entry.get("content", "")
                if len(content) > 200:
                    content = content[:200] + "..."
                parts.append(f"- {entry.get('timestamp', '')} | {content}")

        # Semantic search for relevance
        search = self._memory.search_memory(goal)
        docs = search.get("documents", [])
        if docs:
            parts.append("## Relevant Memory")
            for doc in docs[:3]:
                parts.append(f"- {doc[:150]}")

        # Screen observation
        if screen_observation:
            if "description" in screen_observation:
                parts.append("## Current Screen")
                parts.append(f"Window: {screen_observation.get('window_title', 'unknown')}")
                parts.append(f"Description: {screen_observation['description']}")
            elif "error" in screen_observation:
                parts.append("## Screen Observation")
                parts.append(f"(unavailable: {screen_observation['error']})")

        # Available tools
        parts.append("## Available Tools")
        parts.append(self._registry.format_for_prompt())

        return "\n\n".join(parts)
