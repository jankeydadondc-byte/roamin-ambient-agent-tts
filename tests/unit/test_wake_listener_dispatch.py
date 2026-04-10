"""Unit tests for _try_direct_dispatch() in wake_listener — 9.3.1.

Tests the direct-dispatch routing layer without live audio, keyboard,
llama_cpp, or AgentLoop. Heavy deps are stubbed by conftest.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from agent.core.tool_registry import ToolRegistry

# Heavy deps are pre-stubbed by conftest.py; import the function under test
from agent.core.voice.wake_listener import _try_direct_dispatch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(*tool_names: str) -> ToolRegistry:
    """Return a real ToolRegistry with no-op implementations for each name."""
    reg = ToolRegistry()
    for name in tool_names:
        reg.register(
            name=name,
            description=f"mock {name}",
            risk="low",
            params={},
            implementation=lambda p, _n=name: {"result": f"{_n} called"},
        )
    return reg


# ---------------------------------------------------------------------------
# MemPalace triggers
# ---------------------------------------------------------------------------


def test_mempalace_search_trigger_routes_to_mempalace_search():
    """A 'search my memories' phrase calls mempalace_search, not web_search."""
    reg = _make_registry("mempalace_search", "web_search")
    called = {}

    def _fake_execute(name, params):
        called["name"] = name
        called["params"] = params
        return {"result": "ok"}

    reg.execute = _fake_execute
    _try_direct_dispatch("search my memories for lost keys", reg)
    assert called.get("name") == "mempalace_search"
    assert "lost keys" in called.get("params", {}).get("query", "")


def test_palace_status_trigger_routes_to_mempalace_status():
    """'palace status' phrase calls mempalace_status."""
    reg = _make_registry("mempalace_status", "web_search")
    called = {}

    def _fake_execute(name, params):
        called["name"] = name
        return {"result": "ok"}

    reg.execute = _fake_execute
    _try_direct_dispatch("palace status", reg)
    assert called.get("name") == "mempalace_status"


# ---------------------------------------------------------------------------
# Web search triggers
# ---------------------------------------------------------------------------


def test_web_search_trigger_routes_to_web_search():
    """'search the web for' phrase routes to web_search."""
    reg = _make_registry("web_search")
    called = {}

    def _fake_execute(name, params):
        called["name"] = name
        called["params"] = params
        return {"result": "ok"}

    reg.execute = _fake_execute
    _try_direct_dispatch("search the web for latest python news", reg)
    assert called.get("name") == "web_search"


# ---------------------------------------------------------------------------
# Fall-through
# ---------------------------------------------------------------------------


def test_unrecognized_phrase_returns_none():
    """An unrecognized phrase returns None (falls through to AgentLoop)."""
    reg = _make_registry("web_search", "mempalace_search")
    result = _try_direct_dispatch("tell me a joke", reg)
    assert result is None


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------


def test_dispatch_uses_provided_registry_not_fresh_one():
    """_try_direct_dispatch uses the registry passed in — not a new ToolRegistry()."""
    mock_reg = MagicMock()
    mock_reg.execute.return_value = {"result": "from mock"}
    # Trigger web_search path
    _try_direct_dispatch("web search python tips", mock_reg)
    mock_reg.execute.assert_called_once()
    name_arg = mock_reg.execute.call_args[0][0]
    assert name_arg == "web_search"
