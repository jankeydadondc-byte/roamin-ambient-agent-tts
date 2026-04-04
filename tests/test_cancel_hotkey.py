"""Tests for cancel-hotkey-wiring: second ctrl+space press cancels an active AgentLoop."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import agent.core.voice.wake_listener as wl_mod


def _make_listener():
    """Build a WakeListener with mocked deps. Patches keyboard at module level."""
    stt = MagicMock()
    tts = MagicMock()
    tts.is_available.return_value = True
    agent_loop = MagicMock()
    # Patch the module-level `keyboard` variable so WakeListener.start() can be called
    with patch.object(wl_mod, "keyboard", MagicMock()):
        listener = wl_mod.WakeListener(stt=stt, tts=tts, agent_loop=agent_loop)
    return listener


class TestCancelHotkeyWiring:
    """Task 3.1 — cancel() called when agent is running and lock is held."""

    def test_cancel_called_when_agent_running(self):
        listener = _make_listener()
        # Simulate agent loop is running: hold the lock and set the event
        acquired = listener._wake_lock.acquire(blocking=False)
        assert acquired, "Should be able to acquire lock in test"
        listener._agent_running_event.set()

        try:
            listener._on_wake_thread()
        finally:
            listener._wake_lock.release()

        listener._agent_loop.cancel.assert_called_once()

    def test_cancel_speaks_phrase(self):
        listener = _make_listener()
        acquired = listener._wake_lock.acquire(blocking=False)
        assert acquired
        listener._agent_running_event.set()

        daemon_targets: list = []

        original_init = threading.Thread.__init__

        def _capture_init(self_thread, *args, target=None, daemon=None, **kwargs):
            if daemon:
                daemon_targets.append(target)
            original_init(self_thread, *args, target=target, daemon=daemon, **kwargs)

        with patch.object(threading.Thread, "__init__", _capture_init):
            try:
                listener._on_wake_thread()
            finally:
                listener._wake_lock.release()

        assert len(daemon_targets) == 1, "Expected one daemon thread for TTS speak"
        # Call the captured target directly to verify it calls tts.speak
        daemon_targets[0]()
        listener._tts.speak.assert_called_with("Got it, stopping.")


class TestDebouncePathPreserved:
    """Task 3.2 — cancel() NOT called when lock is held but agent is NOT running."""

    def test_no_cancel_when_agent_not_running(self):
        listener = _make_listener()
        # Hold lock but do NOT set _agent_running_event
        acquired = listener._wake_lock.acquire(blocking=False)
        assert acquired

        try:
            listener._on_wake_thread()
        finally:
            listener._wake_lock.release()

        listener._agent_loop.cancel.assert_not_called()
        listener._tts.speak.assert_not_called()


class TestNormalFlowWhenLockFree:
    """Task 3.3 — normal wake flow when lock is not held."""

    def test_normal_flow_acquires_lock_and_starts_thread(self):
        listener = _make_listener()

        started_threads: list[threading.Thread] = []
        original_start = threading.Thread.start

        def _capture_start(self_thread, *args, **kwargs):
            started_threads.append(self_thread)
            # Replace target with a no-op that releases the lock so the test doesn't hang
            self_thread._target = lambda: listener._wake_lock.release()
            return original_start(self_thread, *args, **kwargs)

        with patch.object(threading.Thread, "start", _capture_start):
            listener._on_wake_thread()

        import time

        time.sleep(0.05)
        assert len(started_threads) == 1, "Expected exactly one wake thread to be started"
        listener._agent_loop.cancel.assert_not_called()
