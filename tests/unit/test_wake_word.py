"""Tests for WakeWordListener — wake word detection (Priority 11.1 / 11.2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from agent.core.voice.wake_word import _FRAME_SAMPLES, WakeWordListener

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_listener(**kwargs) -> WakeWordListener:
    """Create a WakeWordListener with defaults overridden."""
    defaults = {
        "on_detect": None,
        "on_stop_detect": None,
        "threshold": 0.5,
        "wake_model_path": Path("/nonexistent/model.onnx"),
        "stop_model_path": Path("/nonexistent/stop.onnx"),
    }
    defaults.update(kwargs)
    return WakeWordListener(**defaults)


def _silent_frame() -> np.ndarray:
    """Generate a silent audio frame (all zeros)."""
    return np.zeros(_FRAME_SAMPLES, dtype=np.int16)


def _loud_frame(amplitude: int = 5000) -> np.ndarray:
    """Generate a loud audio frame (for energy gate testing)."""
    return np.full(_FRAME_SAMPLES, amplitude, dtype=np.int16)


# ---------------------------------------------------------------------------
# Init and state tests
# ---------------------------------------------------------------------------


class TestWakeWordInit:
    def test_default_state(self):
        listener = _make_listener()
        assert not listener.is_running
        assert not listener.is_paused
        assert not listener.is_available

    def test_threshold_from_constructor(self):
        listener = _make_listener(threshold=0.8)
        assert listener._threshold == 0.8

    def test_start_fails_without_model(self):
        """Start should return False when model doesn't exist."""
        listener = _make_listener()
        result = listener.start()
        assert result is False
        assert not listener.is_running


# ---------------------------------------------------------------------------
# Pause / Resume
# ---------------------------------------------------------------------------


class TestPauseResume:
    def test_pause_sets_flag(self):
        listener = _make_listener()
        listener.pause()
        assert listener.is_paused

    def test_resume_clears_flag(self):
        listener = _make_listener()
        listener.pause()
        listener.resume()
        assert not listener.is_paused

    def test_pause_resume_is_idempotent(self):
        listener = _make_listener()
        listener.pause()
        listener.pause()
        assert listener.is_paused
        listener.resume()
        listener.resume()
        assert not listener.is_paused


# ---------------------------------------------------------------------------
# Wake word detection
# ---------------------------------------------------------------------------


class TestWakeDetection:
    def test_callback_fires_on_detection(self):
        callback = MagicMock()
        listener = _make_listener(on_detect=callback)

        # Mock a wake model that returns high confidence
        mock_model = MagicMock()
        mock_model.predict.return_value = {"hey_roamin": 0.9}
        mock_model.reset = MagicMock()
        listener._wake_model = mock_model

        # Feed a frame
        listener._check_wake_word(_silent_frame())

        callback.assert_called_once()
        mock_model.reset.assert_called_once()

    def test_callback_not_fired_below_threshold(self):
        callback = MagicMock()
        listener = _make_listener(on_detect=callback, threshold=0.8)

        mock_model = MagicMock()
        mock_model.predict.return_value = {"hey_roamin": 0.3}
        listener._wake_model = mock_model

        listener._check_wake_word(_silent_frame())
        callback.assert_not_called()

    def test_cooldown_suppresses_rapid_detections(self):
        callback = MagicMock()
        listener = _make_listener(on_detect=callback)
        listener._detection_cooldown = 5.0  # 5 second cooldown

        mock_model = MagicMock()
        mock_model.predict.return_value = {"hey_roamin": 0.9}
        mock_model.reset = MagicMock()
        listener._wake_model = mock_model

        # First detection fires
        listener._check_wake_word(_silent_frame())
        assert callback.call_count == 1

        # Second detection within cooldown is suppressed
        listener._check_wake_word(_silent_frame())
        assert callback.call_count == 1

    def test_callback_error_is_caught(self):
        """Callback exceptions should not crash the listener."""
        callback = MagicMock(side_effect=RuntimeError("boom"))
        listener = _make_listener(on_detect=callback)

        mock_model = MagicMock()
        mock_model.predict.return_value = {"hey_roamin": 0.9}
        mock_model.reset = MagicMock()
        listener._wake_model = mock_model

        # Should not raise
        listener._check_wake_word(_silent_frame())
        callback.assert_called_once()


# ---------------------------------------------------------------------------
# Stop word detection (11.2)
# ---------------------------------------------------------------------------


class TestStopDetection:
    def test_stop_callback_fires(self):
        stop_cb = MagicMock()
        listener = _make_listener(on_stop_detect=stop_cb)

        mock_model = MagicMock()
        mock_model.predict.return_value = {"stop_roamin": 0.9}
        mock_model.reset = MagicMock()
        listener._stop_model = mock_model

        listener._check_stop_word(_silent_frame())
        stop_cb.assert_called_once()

    def test_energy_gate_suppresses_loud_frames(self):
        """Loud audio (likely TTS echo) should suppress stop detection."""
        stop_cb = MagicMock()
        listener = _make_listener(on_stop_detect=stop_cb)

        mock_model = MagicMock()
        mock_model.predict.return_value = {"stop_roamin": 0.9}
        listener._stop_model = mock_model

        # Loud frame should be gated
        listener._check_stop_word(_loud_frame(amplitude=5000))
        stop_cb.assert_not_called()

    def test_stop_not_fired_below_threshold(self):
        stop_cb = MagicMock()
        listener = _make_listener(on_stop_detect=stop_cb, threshold=0.7)

        mock_model = MagicMock()
        mock_model.predict.return_value = {"stop_roamin": 0.3}
        listener._stop_model = mock_model

        listener._check_stop_word(_silent_frame())
        stop_cb.assert_not_called()


# ---------------------------------------------------------------------------
# Stop listening activation
# ---------------------------------------------------------------------------


class TestStopListeningMode:
    def test_start_stop_listening_pauses_wake(self):
        listener = _make_listener()
        # Mock the stop model as loaded
        listener._stop_model = MagicMock()
        listener.start_stop_listening()
        assert listener._stop_listening_active
        assert listener.is_paused  # Wake paused during TTS

    def test_stop_stop_listening_resumes_wake(self):
        listener = _make_listener()
        listener._stop_model = MagicMock()
        listener.start_stop_listening()
        listener.stop_stop_listening()
        assert not listener._stop_listening_active
        assert not listener.is_paused

    def test_start_stop_without_model_is_noop(self):
        listener = _make_listener()
        # No stop model loaded
        listener.start_stop_listening()
        assert not listener._stop_listening_active


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


class TestModelLoading:
    def test_load_wake_model_missing_openwakeword(self):
        listener = _make_listener()
        with patch.dict("sys.modules", {"openwakeword": None}):
            # Import should fail gracefully
            listener._load_wake_model()
            # May return True if cached, or False if import fails
            # The key is it doesn't crash

    def test_load_stop_model_missing_file(self):
        listener = _make_listener(stop_model_path="/no/such/model.onnx")
        result = listener._load_stop_model()
        assert result is False
