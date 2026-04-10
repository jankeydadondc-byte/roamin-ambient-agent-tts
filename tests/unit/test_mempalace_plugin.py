"""Unit tests for agent.plugins.mempalace — 9.1.3."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import agent.plugins.mempalace as mp_module
from agent.plugins.mempalace import Plugin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry() -> MagicMock:
    """Return a mock registry that tracks register() calls."""
    reg = MagicMock()
    reg._tools: dict = {}

    def _register(name, **kwargs):
        reg._tools[name] = kwargs

    reg.register.side_effect = _register
    return reg


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


def test_plugin_instantiates():
    """Plugin() can be created with zero args."""
    p = Plugin()
    assert p is not None


def test_plugin_name():
    """Plugin.name is 'mempalace_memory'."""
    assert Plugin.name == "mempalace_memory"


# ---------------------------------------------------------------------------
# on_load — plugin mode (registers tools, no subprocess)
# ---------------------------------------------------------------------------


def test_on_load_plugin_mode_registers_both_tools(monkeypatch):
    """on_load() with mode='plugin' registers mempalace_status and mempalace_search."""
    monkeypatch.setattr(mp_module, "_MODE", "plugin")
    p = Plugin()
    reg = _make_registry()
    p.on_load(reg)
    assert "mempalace_status" in reg._tools
    assert "mempalace_search" in reg._tools
    # MCP server should NOT start
    assert p._mcp_proc is None


def test_on_load_standalone_mode_skips_tools(monkeypatch):
    """on_load() with mode='standalone' does NOT register tools."""
    monkeypatch.setattr(mp_module, "_MODE", "standalone")
    p = Plugin()
    reg = _make_registry()
    with patch.object(p, "_start_mcp_server") as mock_start:
        p.on_load(reg)
    assert "mempalace_status" not in reg._tools
    assert "mempalace_search" not in reg._tools
    mock_start.assert_called_once()


# ---------------------------------------------------------------------------
# on_unload
# ---------------------------------------------------------------------------


def test_on_unload_terminates_mcp_proc():
    """on_unload() calls terminate() on _mcp_proc if set."""
    p = Plugin()
    mock_proc = MagicMock()
    p._mcp_proc = mock_proc
    p.on_unload()
    mock_proc.terminate.assert_called_once()


def test_on_unload_no_proc_is_safe():
    """on_unload() with no MCP proc doesn't raise."""
    p = Plugin()
    p.on_unload()  # should not raise


# ---------------------------------------------------------------------------
# _status
# ---------------------------------------------------------------------------


def test_status_returns_result_on_success(monkeypatch, tmp_path):
    """_status() returns {'success': True, 'result': ...} when subprocess succeeds."""
    monkeypatch.setattr(mp_module, "_PALACE_PATH", tmp_path)
    p = Plugin()
    mock_result = MagicMock()
    mock_result.stdout = "Wings: 3, Rooms: 12"
    mock_result.stderr = ""
    with patch("subprocess.run", return_value=mock_result):
        out = p._status({})
    assert out["success"] is True
    assert "result" in out
    assert "Wings" in out["result"]


def test_status_returns_error_on_exception(monkeypatch, tmp_path):
    """_status() returns {'success': False, 'error': ...} when subprocess raises."""
    monkeypatch.setattr(mp_module, "_PALACE_PATH", tmp_path)
    p = Plugin()
    with patch("subprocess.run", side_effect=Exception("timeout")):
        out = p._status({})
    assert out["success"] is False
    assert "error" in out


# ---------------------------------------------------------------------------
# _search
# ---------------------------------------------------------------------------


def test_search_empty_query_returns_error():
    """_search() with empty query returns error without calling search_memories."""
    p = Plugin()
    out = p._search({"query": ""})
    assert out["success"] is False
    assert "query is required" in out["error"]


def test_search_import_error_returns_not_installed(monkeypatch, tmp_path):
    """_search() returns 'not installed' error when mempalace package is missing."""
    monkeypatch.setattr(mp_module, "_PALACE_PATH", tmp_path)
    p = Plugin()
    with patch.dict("sys.modules", {"mempalace.searcher": None}):
        with patch("builtins.__import__", side_effect=ImportError("no mempalace")):
            out = p._search({"query": "test query"})
    assert out["success"] is False
    assert "not installed" in out["error"]


def test_search_formats_hits_into_result_string(monkeypatch, tmp_path):
    """_search() formats returned hits into bullet strings under 'result' key."""
    monkeypatch.setattr(mp_module, "_PALACE_PATH", tmp_path)
    p = Plugin()
    fake_results = {
        "results": [
            {"document": "Memory about cats", "similarity": 0.91},
            {"document": "Memory about dogs", "similarity": 0.85},
        ]
    }
    fake_searcher = MagicMock()
    fake_searcher.search_memories = MagicMock(return_value=fake_results)
    with patch.dict("sys.modules", {"mempalace": MagicMock(), "mempalace.searcher": fake_searcher}):
        out = p._search({"query": "animals"})
    assert out["success"] is True
    assert "Memory about cats" in out["result"]
    assert "Memory about dogs" in out["result"]
