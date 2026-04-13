"""Tests for 4.4: Tool Fallback Chains in ToolRegistry."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent.core.tool_registry import _TOOL_FALLBACKS, ToolRegistry


class TestExecuteSingle:
    """Unit tests for ToolRegistry._execute_single()."""

    def _registry_with_tool(self, name: str, impl, risk: str = "low") -> ToolRegistry:
        reg = ToolRegistry.__new__(ToolRegistry)
        reg._tools = {}
        reg._tools[name] = {"name": name, "risk": risk, "params": {}, "implementation": impl}
        return reg

    def test_success_returns_result(self):
        impl = MagicMock(return_value={"success": True, "result": "ok"})
        reg = self._registry_with_tool("my_tool", impl)
        result = reg._execute_single("my_tool", {"q": "dogs"})
        assert result == {"success": True, "result": "ok"}
        impl.assert_called_once_with({"q": "dogs"})

    def test_unknown_tool_returns_failure(self):
        reg = ToolRegistry.__new__(ToolRegistry)
        reg._tools = {}
        result = reg._execute_single("nonexistent", {})
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    def test_no_implementation_returns_failure(self):
        reg = ToolRegistry.__new__(ToolRegistry)
        reg._tools = {"my_tool": {"name": "my_tool", "risk": "low", "params": {}}}
        result = reg._execute_single("my_tool", {})
        assert result["success"] is False
        assert "No implementation" in result["error"]

    def test_exception_caught_returns_failure(self):
        impl = MagicMock(side_effect=RuntimeError("boom"))
        reg = self._registry_with_tool("my_tool", impl)
        result = reg._execute_single("my_tool", {})
        assert result["success"] is False
        assert "boom" in result["error"]


def _reg_with_tools(*names: str) -> ToolRegistry:
    """Build a ToolRegistry stub with the given tool names pre-registered (all low risk)."""
    reg = ToolRegistry.__new__(ToolRegistry)
    reg._tools = {n: {"name": n, "risk": "low", "params": {}} for n in names}
    return reg


class TestToolFallbackChains:
    """Unit tests for ToolRegistry.execute() fallback behaviour."""

    def test_primary_success_no_fallback(self):
        """If primary succeeds, fallbacks are never tried."""
        reg = _reg_with_tools("web_search")

        success_result = {"success": True, "result": "web result"}
        reg._execute_single = MagicMock(return_value=success_result)

        result = reg.execute("web_search", {"query": "dogs"})
        assert result == success_result
        assert "fallback_used" not in result
        reg._execute_single.assert_called_once_with("web_search", {"query": "dogs"})

    def test_primary_fail_triggers_fallback(self):
        """If primary fails and fallback succeeds, fallback result is returned."""
        reg = _reg_with_tools("web_search", "fetch_url")

        fail_result = {"success": False, "error": "network error"}
        fb_result = {"success": True, "result": "<html>duckduckgo</html>"}

        def _execute_single(name, params):
            if name == "web_search":
                return fail_result
            if name == "fetch_url":
                return fb_result
            return {"success": False, "error": "unexpected"}

        reg._execute_single = MagicMock(side_effect=_execute_single)

        result = reg.execute("web_search", {"query": "dogs"})
        assert result["success"] is True
        assert result["fallback_used"] == "fetch_url"

    def test_fallback_param_adapter_applied(self):
        """Param adapter must transform query -> URL before calling fetch_url."""
        reg = _reg_with_tools("web_search", "fetch_url")

        calls = []

        def _execute_single(name, params):
            calls.append((name, params))
            if name == "web_search":
                return {"success": False, "error": "fail"}
            if name == "fetch_url":
                return {"success": True, "result": "html"}
            return {"success": False, "error": "unexpected"}

        reg._execute_single = MagicMock(side_effect=_execute_single)
        reg.execute("web_search", {"query": "cats"})

        # Second call must be fetch_url with adapted URL
        assert calls[1][0] == "fetch_url"
        assert "cats" in calls[1][1]["url"]

    def test_all_fallbacks_fail_returns_original_error(self):
        """If every fallback also fails, the original primary failure is returned."""
        reg = _reg_with_tools("web_search", "fetch_url")

        fail_result = {"success": False, "error": "primary failed"}

        reg._execute_single = MagicMock(return_value=fail_result)

        result = reg.execute("web_search", {"query": "dogs"})
        assert result["success"] is False
        assert result["error"] == "primary failed"
        assert "fallback_used" not in result

    def test_tool_with_no_fallback_returns_failure_directly(self):
        """Tool not in _TOOL_FALLBACKS should return failure immediately."""
        reg = _reg_with_tools("run_python")

        fail_result = {"success": False, "error": "syntax error"}
        reg._execute_single = MagicMock(return_value=fail_result)

        # run_python is not in _TOOL_FALLBACKS
        assert "run_python" not in _TOOL_FALLBACKS

        result = reg.execute("run_python", {"code": "not valid"})
        assert result["success"] is False
        reg._execute_single.assert_called_once_with("run_python", {"code": "not valid"})

    def test_memory_recall_falls_back_to_memory_search(self):
        """memory_recall -> memory_search fallback with fact_name -> query adapter."""
        reg = _reg_with_tools("memory_recall", "memory_search")

        calls = []

        def _execute_single(name, params):
            calls.append((name, params))
            if name == "memory_recall":
                return {"success": False, "error": "not found"}
            if name == "memory_search":
                return {"success": True, "result": "found something"}
            return {"success": False, "error": "unexpected"}

        reg._execute_single = MagicMock(side_effect=_execute_single)
        result = reg.execute("memory_recall", {"fact_name": "my age"})

        assert result["success"] is True
        assert result["fallback_used"] == "memory_search"
        # Adapter must transform fact_name -> query
        assert calls[1] == ("memory_search", {"query": "my age"})


class TestFallbackTable:
    """Unit tests for _TOOL_FALLBACKS constant structure."""

    def test_web_search_has_fetch_url_fallback(self):
        assert "web_search" in _TOOL_FALLBACKS
        names = [name for name, _ in _TOOL_FALLBACKS["web_search"]]
        assert "fetch_url" in names

    def test_memory_recall_has_memory_search_fallback(self):
        assert "memory_recall" in _TOOL_FALLBACKS
        names = [name for name, _ in _TOOL_FALLBACKS["memory_recall"]]
        assert "memory_search" in names

    def test_all_adapters_are_callable_or_none(self):
        for _tool_name, chain in _TOOL_FALLBACKS.items():
            for _fb_name, adapter in chain:
                assert adapter is None or callable(adapter)
