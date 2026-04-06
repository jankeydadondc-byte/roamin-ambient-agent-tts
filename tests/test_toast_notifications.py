"""Tests for 6.2 — Modern Toast Notifications."""

from unittest.mock import MagicMock, patch

from agent.core.screen_observer import _notify_windows


class TestNotifyWindowsWithWinotify:
    """Verify winotify integration when available."""

    @patch("agent.core.screen_observer.Notification", create=True)
    def test_winotify_show_called_with_correct_args(self, _mock_cls):
        """winotify.Notification is constructed with title and message, then .show() called."""
        mock_instance = MagicMock()
        # Patch the import inside _notify_windows
        with patch("agent.core.screen_observer._notify_windows.__module__", "agent.core.screen_observer"):
            pass
        # We need to patch winotify at the import site
        mock_notification_cls = MagicMock(return_value=mock_instance)
        with patch.dict("sys.modules", {"winotify": MagicMock(Notification=mock_notification_cls)}):
            _notify_windows("Task completed", title="Test Title")

        mock_notification_cls.assert_called_once_with(app_id="Roamin", title="Test Title", msg="Task completed")
        mock_instance.set_audio.assert_called_once()
        mock_instance.show.assert_called_once()

    def test_default_title_is_roamin(self):
        """When title is not provided, default is 'Roamin'."""
        mock_notification_cls = MagicMock(return_value=MagicMock())
        with patch.dict("sys.modules", {"winotify": MagicMock(Notification=mock_notification_cls)}):
            _notify_windows("Hello")

        mock_notification_cls.assert_called_once_with(app_id="Roamin", title="Roamin", msg="Hello")


class TestNotifyWindowsFallback:
    """Verify fallback to WScript.Shell when winotify unavailable."""

    @patch("subprocess.run")
    def test_fallback_to_powershell_when_winotify_missing(self, mock_run):
        """When winotify import fails, PowerShell subprocess is called."""
        # Remove winotify from sys.modules to force ImportError
        with patch.dict("sys.modules", {"winotify": None}):
            _notify_windows("Fallback test")

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "powershell" in call_args[0][0][0].lower() or call_args[0][0] == [
            "powershell",
            "-Command",
        ]

    @patch("subprocess.run")
    def test_fallback_uses_title(self, mock_run):
        """Fallback PowerShell command includes the title."""
        with patch.dict("sys.modules", {"winotify": None}):
            _notify_windows("msg", title="CustomTitle")

        call_args = mock_run.call_args
        ps_command = call_args[0][0][2] if len(call_args[0][0]) > 2 else str(call_args)
        assert "CustomTitle" in ps_command


class TestNotifyWindowsExceptionHandling:
    """Verify exception resilience."""

    def test_winotify_show_exception_caught(self):
        """If winotify.Notification.show() raises, no exception propagates."""
        mock_instance = MagicMock()
        mock_instance.show.side_effect = RuntimeError("toast failed")
        mock_cls = MagicMock(return_value=mock_instance)
        with patch.dict("sys.modules", {"winotify": MagicMock(Notification=mock_cls)}):
            # Should not raise
            _notify_windows("test")

    @patch("subprocess.run", side_effect=OSError("no powershell"))
    def test_fallback_exception_caught(self, _mock_run):
        """If both winotify and PowerShell fail, no exception propagates."""
        with patch.dict("sys.modules", {"winotify": None}):
            # Should not raise
            _notify_windows("test")


class TestNotifyTool:
    """Verify the notify tool in ToolRegistry uses _notify_windows correctly."""

    @patch("agent.core.screen_observer._notify_windows")
    def test_notify_tool_passes_title_and_message(self, mock_notify):
        """The notify tool passes title and message as separate args."""
        from agent.core.tools import _notify

        result = _notify({"title": "MyTitle", "message": "Hello world"})

        mock_notify.assert_called_once_with("Hello world", title="MyTitle")
        assert result.get("success") is True

    def test_notify_tool_rejects_empty_message(self):
        """The notify tool rejects calls with empty or missing message."""
        from agent.core.tools import _notify

        result = _notify({"title": "Test", "message": ""})
        assert result.get("success") is False

        result = _notify({"title": "Test"})
        assert result.get("success") is False
