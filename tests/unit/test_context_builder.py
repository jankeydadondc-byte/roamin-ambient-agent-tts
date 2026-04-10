"""Unit tests for agent.core.context_builder — 9.1.1."""

from __future__ import annotations

from unittest.mock import patch

from agent.core.context_builder import ContextBuilder
from agent.core.tool_registry import ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patched_builder() -> ContextBuilder:
    """Return a ContextBuilder with memory + semantic search mocked out."""
    with patch("agent.core.context_builder.MemoryManager") as MockMem:
        instance = MockMem.return_value
        instance.get_recent_conversations.return_value = []
        instance.search_memory.return_value = {"documents": []}
        cb = ContextBuilder()
        # Patch the live instance too (already created)
        cb._memory = instance
    return cb


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_returns_non_empty_string():
    """build() with no registry returns a non-empty string."""
    cb = _patched_builder()
    result = cb.build("test goal", max_memory_results=0)
    assert isinstance(result, str)
    assert len(result) > 0


def test_build_contains_goal():
    """build() output always contains the goal text."""
    cb = _patched_builder()
    result = cb.build("find my lost keys", max_memory_results=0)
    assert "find my lost keys" in result


def test_build_with_tool_registry_override():
    """build() with registry= override uses that registry's tools in output."""
    cb = _patched_builder()
    reg = ToolRegistry()
    reg.register(
        name="my_custom_tool",
        description="does something unique",
        risk="low",
        params={},
        implementation=lambda p: {"result": "ok"},
    )
    result = cb.build("test goal", max_memory_results=0, registry=reg)
    assert "my_custom_tool" in result


def test_build_with_screen_observation():
    """build() with screen_observation dict includes observation in output."""
    cb = _patched_builder()
    obs = {"description": "VS Code open", "window_title": "editor"}
    result = cb.build("check screen", screen_observation=obs, max_memory_results=0)
    assert "VS Code open" in result or "editor" in result


def test_build_max_memory_results_zero_does_not_crash():
    """build() with max_memory_results=0 completes without error."""
    cb = _patched_builder()
    result = cb.build("goal", max_memory_results=0)
    assert result is not None
