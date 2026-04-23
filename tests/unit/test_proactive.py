"""Tests for ProactiveEngine — proactive notifications (Priority 11.5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.core.proactive import _MEETING_APP_PATTERNS, Notification, ProactiveEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(**kwargs) -> ProactiveEngine:
    defaults = {
        "tray": MagicMock(),
        "tts": MagicMock(),
        "process_interval": 0.1,
    }
    defaults.update(kwargs)
    return ProactiveEngine(**defaults)


# ---------------------------------------------------------------------------
# Notification dataclass
# ---------------------------------------------------------------------------


class TestNotification:
    def test_priority_ordering(self):
        n1 = Notification(priority=1, message="urgent")
        n2 = Notification(priority=5, message="normal")
        n3 = Notification(priority=10, message="low")
        assert n1 < n2 < n3

    def test_defaults(self):
        n = Notification(priority=5, message="test")
        assert n.source == "system"
        assert not n.delivered
        assert not n.cancelled
        assert n.timestamp > 0


# ---------------------------------------------------------------------------
# Queue management
# ---------------------------------------------------------------------------


class TestQueueManagement:
    def test_queue_notification(self):
        engine = _make_engine()
        engine.queue_notification("Hello bud", priority=3, source="timer")
        assert engine.queue_size == 1

    def test_queue_ordering_by_priority(self):
        engine = _make_engine()
        engine.queue_notification("low priority", priority=10)
        engine.queue_notification("high priority", priority=1)
        engine.queue_notification("medium priority", priority=5)

        # PriorityQueue should return highest priority (lowest number) first
        n1 = engine._queue.get_nowait()
        n2 = engine._queue.get_nowait()
        n3 = engine._queue.get_nowait()
        assert n1.message == "high priority"
        assert n2.message == "medium priority"
        assert n3.message == "low priority"

    def test_queue_default_priority(self):
        engine = _make_engine()
        engine.queue_notification("test")
        n = engine._queue.get_nowait()
        assert n.priority == 5


# ---------------------------------------------------------------------------
# Delivery flow
# ---------------------------------------------------------------------------


class TestDeliveryFlow:
    def test_step1_tray_flash(self):
        tray = MagicMock()
        engine = _make_engine(tray=tray)

        notif = Notification(priority=5, message="test")
        with (
            patch.object(engine, "is_in_meeting", return_value=False),
            patch.object(engine, "_show_popup", return_value=False),
        ):
            engine._deliver(notif)

        tray.flash.assert_called_once()

    def test_step3_tts_speaks(self):
        tts = MagicMock()
        tts.is_available.return_value = True
        engine = _make_engine(tts=tts)

        notif = Notification(priority=5, message="Hey bud")
        with (
            patch.object(engine, "is_in_meeting", return_value=False),
            patch.object(engine, "_show_popup", return_value=False),
        ):
            engine._deliver(notif)

        tts.speak_streaming.assert_called_once_with("Hey bud")
        assert notif.delivered

    def test_cancelled_stores_for_chat(self):
        engine = _make_engine()
        notif = Notification(priority=5, message="Test message")

        with (
            patch.object(engine, "is_in_meeting", return_value=False),
            patch.object(engine, "_show_popup", return_value=True),
        ):
            engine._deliver(notif)

        assert notif.cancelled
        pending = engine.get_pending_messages()
        assert len(pending) == 1
        assert pending[0]["message"] == "Test message"
        assert pending[0]["cancelled"] is True

    def test_on_cancelled_callback_fires(self):
        cb = MagicMock()
        engine = _make_engine(on_cancelled=cb)
        notif = Notification(priority=5, message="Cancelled msg")

        with (
            patch.object(engine, "is_in_meeting", return_value=False),
            patch.object(engine, "_show_popup", return_value=True),
        ):
            engine._deliver(notif)

        cb.assert_called_once_with("Cancelled msg")


# ---------------------------------------------------------------------------
# Quiet mode (meeting detection)
# ---------------------------------------------------------------------------


class TestQuietMode:
    def test_meeting_suppresses_tts(self):
        tts = MagicMock()
        tray = MagicMock()
        engine = _make_engine(tts=tts, tray=tray)

        notif = Notification(priority=5, message="Test")
        with patch.object(engine, "is_in_meeting", return_value=True):
            engine._deliver(notif)

        # TTS should NOT be called
        tts.speak_streaming.assert_not_called()
        # Tray flash should still happen (step 1)
        tray.flash.assert_called_once()
        # Message should be queued for chat
        pending = engine.get_pending_messages()
        assert len(pending) == 1

    def test_meeting_window_patterns(self):
        assert "zoom" in _MEETING_APP_PATTERNS
        assert "teams" in _MEETING_APP_PATTERNS
        assert "google meet" in _MEETING_APP_PATTERNS
        assert "discord" in _MEETING_APP_PATTERNS

    def test_meeting_detection_with_zoom(self):
        engine = _make_engine()
        with (
            patch("win32gui.GetForegroundWindow", return_value=123),
            patch("win32gui.GetWindowText", return_value="Zoom Meeting"),
        ):
            assert engine.is_in_meeting()

    def test_no_meeting(self):
        engine = _make_engine()
        with (
            patch("win32gui.GetForegroundWindow", return_value=123),
            patch("win32gui.GetWindowText", return_value="Visual Studio Code"),
        ):
            assert not engine.is_in_meeting()


# ---------------------------------------------------------------------------
# Pending messages
# ---------------------------------------------------------------------------


class TestPendingMessages:
    def test_get_pending_clears_list(self):
        engine = _make_engine()
        engine._pending_chat_messages.append({"message": "test", "source": "system"})
        messages = engine.get_pending_messages()
        assert len(messages) == 1
        # Second call should return empty
        assert len(engine.get_pending_messages()) == 0

    def test_pending_message_format(self):
        engine = _make_engine()
        notif = Notification(priority=3, message="Reminder", source="timer")
        engine._store_for_chat(notif)
        messages = engine.get_pending_messages()
        assert messages[0]["message"] == "Reminder"
        assert messages[0]["source"] == "timer"
        assert messages[0]["priority"] == 3
        assert "timestamp" in messages[0]


# ---------------------------------------------------------------------------
# Enable / disable
# ---------------------------------------------------------------------------


class TestEnableDisable:
    def test_enabled_by_default(self):
        engine = _make_engine()
        assert engine.enabled

    def test_disable(self):
        engine = _make_engine()
        engine.enabled = False
        assert not engine.enabled

    def test_toggle(self):
        engine = _make_engine()
        engine.enabled = False
        engine.enabled = True
        assert engine.enabled


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------


class TestStartStop:
    def test_start_creates_thread(self):
        engine = _make_engine()
        engine.start()
        assert engine.is_running
        engine.stop()
        assert not engine.is_running

    def test_double_start_is_safe(self):
        engine = _make_engine()
        engine.start()
        engine.start()
        assert engine.is_running
        engine.stop()
