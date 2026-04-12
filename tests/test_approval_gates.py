"""Tests for approval gates — pre-execution hook wired into ToolRegistry.execute()."""

from unittest.mock import MagicMock, patch

import pytest

from agent.core.tool_registry import ToolRegistry


@pytest.fixture
def registry():
    """ToolRegistry with a mocked store injected (mirrors run_wake_listener.py wiring)."""
    reg = ToolRegistry()
    reg.store = MagicMock()
    return reg


@pytest.fixture
def mock_toast():
    """Suppress real toast notifications (chromadb unavailable in tests).

    Injects a fake agent.core.screen_observer module into sys.modules so that
    the lazy import inside approve_before_execution() picks up the mock.
    """
    mock_fn = MagicMock()
    mock_module = MagicMock()
    mock_module._notify_approval_toast = mock_fn
    with patch.dict("sys.modules", {"agent.core.screen_observer": mock_module}):
        yield mock_fn


def _approved_store(registry):
    """Configure registry.store to simulate an approved HIGH-risk tool."""
    registry.store.create_pending_approval.return_value = 42
    registry.store.poll_approval_resolution.return_value = {
        "status": "approved",
        "reason": "",
    }


def _denied_store(registry):
    """Configure registry.store to simulate a denied HIGH-risk tool."""
    registry.store.create_pending_approval.return_value = 43
    registry.store.poll_approval_resolution.return_value = {
        "status": "denied",
        "reason": "user_denied",
    }


def _timeout_store(registry):
    """Configure registry.store to simulate an approval timeout."""
    registry.store.create_pending_approval.return_value = 44
    registry.store.poll_approval_resolution.return_value = {
        "status": "timeout",
        "reason": "timeout",
    }


# ---------------------------------------------------------------------------
# Risk level routing
# ---------------------------------------------------------------------------


class TestRiskLevelRouting:
    """LOW and MEDIUM risk tools must skip the approval gate entirely."""

    def test_low_risk_executes_immediately(self, registry, mock_toast):
        """LOW risk tool runs without creating a pending_approval."""
        impl = MagicMock(return_value={"success": True, "result": "read_ok"})
        registry.register("_test_low", "Test low", "low", {"path": "str"}, impl)

        result = registry.execute("_test_low", {"path": "test.txt"})

        assert result["success"] is True
        registry.store.create_pending_approval.assert_not_called()
        mock_toast.assert_not_called()

    def test_medium_risk_executes_immediately(self, registry, mock_toast):
        """MEDIUM risk tool runs without creating a pending_approval."""
        impl = MagicMock(return_value={"success": True, "result": "fetched"})
        registry.register("_test_med", "Test med", "medium", {"url": "str"}, impl)

        result = registry.execute("_test_med", {"url": "http://example.com"})

        assert result["success"] is True
        registry.store.create_pending_approval.assert_not_called()
        mock_toast.assert_not_called()

    def test_high_risk_creates_pending_approval(self, registry, mock_toast):
        """HIGH risk tool creates a pending_approval entry before execution."""
        _approved_store(registry)
        impl = MagicMock(return_value={"success": True, "result": "ran"})
        registry.register("_test_high", "Test high", "high", {"code": "str"}, impl)

        registry.execute("_test_high", {"code": "1+1"})

        registry.store.create_pending_approval.assert_called_once()
        kwargs = registry.store.create_pending_approval.call_args.kwargs
        assert kwargs.get("tool") == "_test_high"
        assert kwargs.get("risk") == "high"


# ---------------------------------------------------------------------------
# Approval outcomes
# ---------------------------------------------------------------------------


class TestApprovalOutcomes:
    """Verify correct behavior on approved / denied / timeout."""

    def test_approved_tool_executes(self, registry, mock_toast):
        """Approved HIGH-risk tool runs and returns its result."""
        _approved_store(registry)
        impl = MagicMock(return_value={"success": True, "result": "code_ran"})
        registry.register("_test_high", "Test high", "high", {"code": "str"}, impl)

        result = registry.execute("_test_high", {"code": "print('hi')"})

        assert result["success"] is True
        impl.assert_called_once()

    def test_denied_returns_structured_error(self, registry, mock_toast):
        """Denied approval returns structured error; tool implementation NOT called."""
        _denied_store(registry)
        impl = MagicMock(return_value={"success": True})
        registry.register("_test_high", "Test high", "high", {"code": "str"}, impl)

        result = registry.execute("_test_high", {"code": "print('hi')"})

        assert result["success"] is False
        assert result["error_type"] == "approval_denied"
        assert "user_denied" in result["message"]
        impl.assert_not_called()

    def test_timeout_returns_structured_error(self, registry, mock_toast):
        """Timed-out approval returns structured error; tool implementation NOT called."""
        _timeout_store(registry)
        impl = MagicMock(return_value={"success": True})
        registry.register("_test_high", "Test high", "high", {"code": "str"}, impl)

        result = registry.execute("_test_high", {"code": "..."})

        assert result["success"] is False
        assert result["error_type"] == "approval_timeout"
        impl.assert_not_called()


# ---------------------------------------------------------------------------
# Toast notifications
# ---------------------------------------------------------------------------


class TestToastNotifications:
    """Verify toast is fired for HIGH-risk tools, not for LOW-risk tools."""

    def test_toast_fires_on_high_risk(self, registry, mock_toast):
        """Toast notification includes tool name in title."""
        _denied_store(registry)  # outcome doesn't matter here — denied is fine
        registry.register("_test_high", "Test high", "high", {"code": "str"}, MagicMock(return_value={"success": True}))

        registry.execute("_test_high", {"code": "1+1"})

        mock_toast.assert_called_once()
        # Called as positional: _notify_approval_toast(aid, action, tool, port)
        args = mock_toast.call_args.args
        assert args[0] == 43  # aid from _denied_store
        assert args[2] == "_test_high"  # tool name

    def test_toast_not_fired_for_low_risk(self, registry, mock_toast):
        """No toast for LOW-risk tool."""
        registry.register("_test_low", "Test low", "low", {}, MagicMock(return_value={"success": True, "result": "ok"}))

        registry.execute("_test_low", {})

        mock_toast.assert_not_called()


# ---------------------------------------------------------------------------
# ROAMIN_SKIP_APPROVAL bypass
# ---------------------------------------------------------------------------


class TestSkipApprovalBypass:
    """_SKIP_APPROVAL=True must bypass the approval gate entirely.

    Note: ROAMIN_SKIP_APPROVAL is now read once at module import time (finding #53 fix).
    Tests patch the module-level constant directly instead of the environment variable.
    """

    def test_skip_approval_bypasses_gate(self, registry, mock_toast):
        """HIGH-risk tool runs immediately when skip flag is True."""
        impl = MagicMock(return_value={"success": True, "result": "ran_without_approval"})
        registry.register("_test_high", "Test high", "high", {"code": "str"}, impl)

        with patch("agent.core.tool_registry._SKIP_APPROVAL", True):
            result = registry.execute("_test_high", {"code": "print('hi')"})

        assert result["success"] is True
        registry.store.create_pending_approval.assert_not_called()
        mock_toast.assert_not_called()
        impl.assert_called_once()

    def test_skip_approval_writes_audit_warning(self, registry, mock_toast):
        """Skip mode writes a warning entry with tool='skip_approval'."""
        impl = MagicMock(return_value={"success": True, "result": "ok"})
        registry.register("_test_high", "Test high", "high", {"code": "str"}, impl)

        with patch("agent.core.audit_log.append") as mock_append:
            with patch("agent.core.tool_registry._SKIP_APPROVAL", True):
                registry.execute("_test_high", {"code": "..."})

        all_calls = mock_append.call_args_list
        skip_warning_calls = [c for c in all_calls if c.kwargs.get("tool") == "skip_approval"]
        assert len(skip_warning_calls) == 1

    def test_skip_false_does_not_bypass(self, registry, mock_toast):
        """_SKIP_APPROVAL=False must NOT bypass — approval gate activates normally."""
        impl = MagicMock(return_value={"success": True, "result": "ok"})
        registry.register("_test_high", "Test high", "high", {"code": "str"}, impl)

        with patch("agent.core.tool_registry._SKIP_APPROVAL", False):
            _approved_store(registry)
            registry.execute("_test_high", {"code": "..."})

        registry.store.create_pending_approval.assert_called()


# ---------------------------------------------------------------------------
# Registered HIGH-risk tools from defaults
# ---------------------------------------------------------------------------


class TestBuiltinHighRiskTools:
    """Spot-check that default registrations carry the correct risk level."""

    HIGH_RISK = ["run_python", "run_powershell", "run_cmd", "write_file", "delete_file", "move_file"]
    LOW_RISK = ["read_file", "list_directory", "glob", "grep", "git_status", "git_log"]

    def test_builtins_are_high_risk(self):
        reg = ToolRegistry()
        for name in self.HIGH_RISK:
            tool = reg.get(name)
            assert tool is not None, f"Tool not registered: {name}"
            assert tool.get("risk") == "high", f"{name} expected high, got {tool.get('risk')}"

    def test_builtins_are_low_risk(self):
        reg = ToolRegistry()
        for name in self.LOW_RISK:
            tool = reg.get(name)
            assert tool is not None, f"Tool not registered: {name}"
            assert tool.get("risk") == "low", f"{name} expected low, got {tool.get('risk')}"


# ---------------------------------------------------------------------------
# Finding #101 — Unknown tool must be denied, not silently approved
# ---------------------------------------------------------------------------


class TestUnknownToolDenial:
    """Unknown tool names must return a denial error — finding #52/#101 regression."""

    def test_unknown_tool_denied(self, registry, mock_toast):
        """Unregistered tool name returns unknown_tool error, never succeeds."""
        result = registry.execute("definitely_not_a_real_tool_xyz", {})

        assert result["success"] is False
        assert result["error_type"] == "unknown_tool"
        mock_toast.assert_not_called()

    def test_unknown_tool_does_not_create_approval(self, registry, mock_toast):
        """Unknown tool must be rejected before the approval gate, not after."""
        result = registry.execute("nonexistent_tool", {"param": "value"})

        assert result["success"] is False
        registry.store.create_pending_approval.assert_not_called()


# ---------------------------------------------------------------------------
# Finding #100 — Chat path (store=None) must BLOCK HIGH-risk tools
# ---------------------------------------------------------------------------


class TestChatPathApprovalBypass:
    """Verify chat path (no store injected) blocks HIGH-risk tools — finding #51 regression."""

    def test_no_store_blocks_high_risk_tool(self, mock_toast):
        """HIGH-risk tool on store-less registry returns approval_unavailable error."""
        reg = ToolRegistry()
        # Deliberately do NOT inject reg.store — mirrors pre-fix chat path
        impl = MagicMock(return_value={"success": True, "result": "ran"})
        reg.register("_test_high_chat", "Test", "high", {"code": "str"}, impl)

        result = reg.execute("_test_high_chat", {"code": "print('hi')"})

        assert result["success"] is False
        assert result["error_type"] == "approval_unavailable"
        impl.assert_not_called()

    def test_no_store_allows_low_risk_tool(self, mock_toast):
        """LOW-risk tools on store-less registry still execute immediately."""
        reg = ToolRegistry()
        impl = MagicMock(return_value={"success": True, "result": "read_ok"})
        reg.register("_test_low_chat", "Test", "low", {"path": "str"}, impl)

        result = reg.execute("_test_low_chat", {"path": "test.txt"})

        assert result["success"] is True
        impl.assert_called_once()

    def test_store_injection_enables_approval_flow(self, mock_toast):
        """After store injection (like chat_engine does), approval gate activates normally."""
        reg = ToolRegistry()
        reg.store = MagicMock()
        reg.store.create_pending_approval.return_value = 99
        reg.store.poll_approval_resolution.return_value = {"status": "approved", "reason": ""}

        impl = MagicMock(return_value={"success": True, "result": "ran"})
        reg.register("_test_high_injected", "Test", "high", {"code": "str"}, impl)

        result = reg.execute("_test_high_injected", {"code": "1+1"})

        assert result["success"] is True
        reg.store.create_pending_approval.assert_called_once()
        impl.assert_called_once()
