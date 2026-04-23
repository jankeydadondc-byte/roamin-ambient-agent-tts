"""Tests for RoaminTray — system tray icon (Priority 11.3a)."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent.core.tray import _STATE_COLORS, RoaminTray, _make_icon_image

# ---------------------------------------------------------------------------
# Icon image generation
# ---------------------------------------------------------------------------


class TestIconImages:
    def test_make_icon_image_returns_rgba(self):
        img = _make_icon_image((255, 0, 0))
        assert img.mode == "RGBA"
        assert img.size == (64, 64)

    def test_all_states_have_colors(self):
        expected = {"idle", "awake", "thinking", "speaking", "error", "privacy_pause"}
        assert set(_STATE_COLORS.keys()) == expected

    def test_all_state_icons_generated(self):
        tray = RoaminTray()
        assert len(tray._icons) == len(_STATE_COLORS)
        for state in _STATE_COLORS:
            assert state in tray._icons


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


class TestStateManagement:
    def test_default_state_is_idle(self):
        tray = RoaminTray()
        assert tray.state == "idle"

    def test_set_valid_state(self):
        tray = RoaminTray()
        for state in _STATE_COLORS:
            tray.set_state(state)
            assert tray.state == state

    def test_set_invalid_state_ignored(self):
        tray = RoaminTray()
        tray.set_state("nonexistent")
        assert tray.state == "idle"  # unchanged

    def test_state_transitions(self):
        tray = RoaminTray()
        transitions = ["idle", "awake", "thinking", "speaking", "idle"]
        for state in transitions:
            tray.set_state(state)
            assert tray.state == state


# ---------------------------------------------------------------------------
# Menu callbacks
# ---------------------------------------------------------------------------


class TestMenuCallbacks:
    def test_open_chat_callback(self):
        cb = MagicMock()
        tray = RoaminTray(on_open_chat=cb)
        tray._handle_open_chat()
        cb.assert_called_once()

    def test_toggle_screenshots(self):
        cb = MagicMock()
        tray = RoaminTray(on_toggle_screenshots=cb)
        assert tray.screenshots_enabled is True

        tray._handle_toggle_screenshots()
        assert tray.screenshots_enabled is False
        cb.assert_called_once_with(False)

        tray._handle_toggle_screenshots()
        assert tray.screenshots_enabled is True

    def test_toggle_proactive(self):
        cb = MagicMock()
        tray = RoaminTray(on_toggle_proactive=cb)
        assert tray.proactive_enabled is True

        tray._handle_toggle_proactive()
        assert tray.proactive_enabled is False
        cb.assert_called_once_with(False)

    def test_restart_callback(self):
        cb = MagicMock()
        tray = RoaminTray(on_restart=cb)
        tray._handle_restart()
        cb.assert_called_once()

    def test_quit_callback(self):
        cb = MagicMock()
        tray = RoaminTray(on_quit=cb)
        tray._handle_quit()
        cb.assert_called_once()

    def test_callback_error_is_caught(self):
        cb = MagicMock(side_effect=RuntimeError("boom"))
        tray = RoaminTray(on_open_chat=cb)
        # Should not raise
        tray._handle_open_chat()
        cb.assert_called_once()

    def test_no_callback_is_safe(self):
        tray = RoaminTray()  # All callbacks None
        # None of these should raise
        tray._handle_open_chat()
        tray._handle_toggle_screenshots()
        tray._handle_toggle_proactive()
        tray._handle_restart()
        tray._handle_quit()
