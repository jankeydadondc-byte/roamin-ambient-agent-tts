"""Wake word detection — OpenWakeWord integration for "Hey Roamin" trigger.

Runs a background daemon thread that reads mic audio in 80ms frames via
sounddevice and feeds them to an OpenWakeWord ONNX model. When the wake
phrase is detected above the confidence threshold, a callback fires.

Also supports a secondary "stop word" model that runs ONLY during TTS
playback to let the user interrupt speech (11.2).

Part of Priority 11.1 / 11.2 — Ambient Presence.

Pre-requisites:
  - pip install openwakeword
  - Train custom model via Google Colab and save to models/wake_word/hey_roamin.onnx
  - (Optional) Train stop model and save to models/wake_word/stop_roamin.onnx
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# --- Model paths ---
_MODELS_DIR = Path(__file__).parents[3] / "models" / "wake_word"
_WAKE_MODEL_PATH = _MODELS_DIR / "hey_roamin.onnx"
_STOP_MODEL_PATH = _MODELS_DIR / "stop_roamin.onnx"

# --- Defaults ---
_DEFAULT_THRESHOLD = float(os.environ.get("ROAMIN_WAKE_THRESHOLD", "0.5"))
_FRAME_MS = 80  # 80ms frames — OpenWakeWord default chunk size
_SAMPLE_RATE = 16000  # 16kHz mono — required by OpenWakeWord
_FRAME_SAMPLES = int(_SAMPLE_RATE * _FRAME_MS / 1000)  # 1280 samples per frame

# Energy gate threshold for echo suppression during stop-word detection.
# When speaker output produces loud audio picked up by the mic, we suppress
# stop-word detections to avoid self-triggering.
_ENERGY_GATE_RMS = 1500  # Stop-word: suppress when speaker output is this loud (echo suppression)
_WAKE_ENERGY_MIN_RMS = 150  # Wake-word: skip detection when frame is quieter than this


class WakeWordListener:
    """Background wake word detector using OpenWakeWord.

    Usage:
        def on_wake():
            print("Wake word detected!")

        listener = WakeWordListener(on_detect=on_wake)
        listener.start()
        # ... later ...
        listener.stop()

    The listener runs a daemon thread that continuously reads from the
    default microphone. It can be paused/resumed (e.g., during STT recording)
    to avoid interference.
    """

    def __init__(
        self,
        on_detect: Callable[[], None] | None = None,
        on_stop_detect: Callable[[], None] | None = None,
        threshold: float = _DEFAULT_THRESHOLD,
        wake_model_path: Path | str | None = None,
        stop_model_path: Path | str | None = None,
    ) -> None:
        self._on_detect = on_detect
        self._on_stop_detect = on_stop_detect
        self._threshold = threshold
        self._wake_model_path = Path(wake_model_path) if wake_model_path else _WAKE_MODEL_PATH
        self._stop_model_path = Path(stop_model_path) if stop_model_path else _STOP_MODEL_PATH

        self._running = False
        self._paused = False
        self._stop_listening_active = False
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

        # Models — lazy loaded
        self._wake_model = None
        self._stop_model = None

        # State tracking
        self._is_available = False
        self._last_detection_time: float = 0
        self._detection_cooldown = 2.0  # seconds between detections
        # Discard this many frames at startup before allowing detections.
        # At 80ms/frame, 25 frames = 2 seconds — avoids firing on ambient
        # noise before the mic has settled.
        self._startup_frames_remaining = 25
        # Rolling buffer of recent audio frames (~2s) for detection capture.
        # When a detection fires, the last ~2s of audio is written to disk
        # under logs/wake_triggers/ for post-hoc inspection.
        self._recent_frames: list[np.ndarray] = []
        self._recent_frames_max = 25  # ~2s at 80ms/frame

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """True if openwakeword loaded successfully and a wake model exists."""
        return self._is_available

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    def start(self) -> bool:
        """Start the wake word listener thread. Returns True if started successfully."""
        if self._running:
            logger.warning("WakeWordListener already running")
            return True

        # Try to load the wake model
        if not self._load_wake_model():
            logger.warning("Wake word model not available — listener not started")
            return False

        self._running = True
        self._paused = False
        self._thread = threading.Thread(
            target=self._listen_loop,
            name="wake-word-listener",
            daemon=True,
        )
        self._thread.start()
        logger.info("WakeWordListener started (threshold=%.2f)", self._threshold)
        return True

    def stop(self) -> None:
        """Stop the wake word listener thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("WakeWordListener stopped")

    def pause(self) -> None:
        """Pause detection (e.g., during STT recording). Thread keeps running but skips frames."""
        with self._lock:
            self._paused = True
        logger.debug("WakeWordListener paused")

    def resume(self) -> None:
        """Resume detection after pause.

        Resets the wake model state and applies a short post-resume warmup
        to discard stale OWW features and room echo from TTS playback.
        """
        if self._wake_model is not None:
            try:
                self._wake_model.reset()
            except Exception:
                pass
        with self._lock:
            self._paused = False
            # Discard first ~1s of frames after resume to let room echo die down.
            # 12 frames × 80ms = 960ms
            self._startup_frames_remaining = max(self._startup_frames_remaining, 12)
        logger.debug("WakeWordListener resumed")

    def start_stop_listening(self) -> None:
        """Activate the stop-word model (call before TTS playback starts).

        The stop model runs concurrently with the main wake model but only
        fires its callback while this mode is active. The wake model is
        paused during TTS to avoid "hey roamin" self-triggers.
        """
        if not self._load_stop_model():
            logger.debug("Stop model not available — stop listening not activated")
            return
        with self._lock:
            self._stop_listening_active = True
            self._paused = True  # Pause wake detection during TTS
        logger.debug("Stop-word listening activated")

    def stop_stop_listening(self) -> None:
        """Deactivate the stop-word model (call after TTS playback ends)."""
        with self._lock:
            self._stop_listening_active = False
            self._paused = False  # Resume wake detection
        logger.debug("Stop-word listening deactivated")

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_wake_model(self) -> bool:
        """Load the wake word ONNX model. Returns True on success."""
        if self._wake_model is not None:
            return True

        try:
            import openwakeword
            from openwakeword.model import Model as OWWModel
        except ImportError:
            logger.warning("openwakeword not installed — wake word detection unavailable")
            return False

        if not self._wake_model_path.exists():
            # Custom model not trained yet — fall back to built-in "hey_jarvis"
            # "Hey Jarvis" is phonetically close enough to use as a placeholder.
            # Train hey_roamin.onnx via Google Colab to replace this.
            logger.info(
                "Custom wake model not found at %s — falling back to built-in 'hey_jarvis'",
                self._wake_model_path,
            )
            try:
                openwakeword.utils.download_models()
                self._wake_model = OWWModel(
                    wakeword_models=["hey_jarvis"],
                    inference_framework="onnx",
                )
                self._is_available = True
                print(
                    '[Roamin] Wake word: using "Hey Jarvis" as placeholder '
                    "(train hey_roamin.onnx to use 'Hey Roamin')",
                    flush=True,
                )
                return True
            except Exception as e:
                logger.warning("Failed to load built-in 'hey_jarvis' model: %s", e)
                return False

        try:
            self._wake_model = OWWModel(
                wakeword_models=[str(self._wake_model_path)],
                inference_framework="onnx",
            )
            self._is_available = True
            logger.info("Wake model loaded: %s", self._wake_model_path.name)
            return True
        except Exception as e:
            logger.warning("Failed to load wake model %s: %s", self._wake_model_path, e)
            return False

    def _load_stop_model(self) -> bool:
        """Load the stop word ONNX model. Returns True on success."""
        if self._stop_model is not None:
            return True

        if not self._stop_model_path.exists():
            logger.debug("Stop model not found at %s", self._stop_model_path)
            return False

        try:
            from openwakeword.model import Model as OWWModel

            self._stop_model = OWWModel(
                wakeword_models=[str(self._stop_model_path)],
                inference_framework="onnx",
            )
            logger.info("Stop model loaded: %s", self._stop_model_path.name)
            return True
        except Exception as e:
            logger.warning("Failed to load stop model %s: %s", self._stop_model_path, e)
            return False

    # ------------------------------------------------------------------
    # Detection loop
    # ------------------------------------------------------------------

    def _listen_loop(self) -> None:
        """Main detection loop — runs on daemon thread."""
        try:
            import sounddevice as sd
        except ImportError:
            logger.error("sounddevice not installed — wake word listener cannot run")
            self._running = False
            return

        logger.info("Wake word listener thread started — reading mic at %dHz", _SAMPLE_RATE)

        try:
            with sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=_FRAME_SAMPLES,
            ) as stream:
                while self._running:
                    # Read one frame from mic
                    try:
                        audio_frame, overflowed = stream.read(_FRAME_SAMPLES)
                    except Exception as e:
                        logger.warning("Mic read error: %s", e)
                        time.sleep(0.1)
                        continue

                    if overflowed:
                        logger.debug("Audio buffer overflowed — frame dropped")
                        continue

                    # Convert to flat int16 array
                    frame_data = audio_frame.flatten().astype(np.int16)

                    with self._lock:
                        paused = self._paused
                        stop_active = self._stop_listening_active

                    # Stop-word detection (during TTS playback)
                    if stop_active and self._stop_model is not None:
                        self._check_stop_word(frame_data)

                    # Maintain rolling audio buffer (used for trigger-capture diagnostics)
                    self._recent_frames.append(frame_data.copy())
                    if len(self._recent_frames) > self._recent_frames_max:
                        self._recent_frames.pop(0)

                    # Wake word detection (skip if paused or still warming up)
                    if not paused and self._wake_model is not None:
                        if self._startup_frames_remaining > 0:
                            self._startup_frames_remaining -= 1
                        else:
                            self._check_wake_word(frame_data)

        except Exception as e:
            logger.error("Wake word listener thread crashed: %s", e)
        finally:
            self._running = False
            logger.info("Wake word listener thread exited")

    def _check_wake_word(self, frame: np.ndarray) -> None:
        """Feed frame to wake model and fire callback on detection."""
        # Energy gate: skip frames that are too quiet to be real speech.
        # False positives from fan/ambient noise have RMS ~27-70; real voice ~1000+.
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        if rms < _WAKE_ENERGY_MIN_RMS:
            return

        try:
            prediction = self._wake_model.predict(frame)
        except Exception as e:
            logger.debug("Wake model prediction error: %s", e)
            return

        # Check all model outputs against threshold
        for model_name, score in prediction.items():
            if score >= self._threshold:
                now = time.time()
                if now - self._last_detection_time < self._detection_cooldown:
                    logger.debug("Wake detection suppressed (cooldown): %s=%.3f", model_name, score)
                    return

                self._last_detection_time = now
                logger.info("Wake word detected: %s (score=%.3f, threshold=%.2f)", model_name, score, self._threshold)

                # Save the ~2s of audio that triggered detection so the user
                # can listen to what matched. Writes to logs/wake_triggers/.
                try:
                    self._save_trigger_audio(model_name, score)
                except Exception as e:
                    logger.debug("Failed to save trigger audio: %s", e)

                # Reset model scores to avoid retriggering
                self._wake_model.reset()

                if self._on_detect:
                    try:
                        self._on_detect()
                    except Exception as e:
                        logger.error("Wake callback error: %s", e)

    def _save_trigger_audio(self, model_name: str, score: float) -> None:
        """Write the rolling audio buffer to a WAV file for post-hoc inspection."""
        if not self._recent_frames:
            return
        import wave
        from datetime import datetime

        out_dir = Path(__file__).parents[3] / "logs" / "wake_triggers"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}_{model_name}_s{int(score*1000):03d}.wav"
        path = out_dir / fname
        audio = np.concatenate(self._recent_frames).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(_SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        logger.info("Trigger audio saved: %s", path.name)

    def _check_stop_word(self, frame: np.ndarray) -> None:
        """Feed frame to stop model and fire callback on detection.

        Includes an energy gate: if the mic is picking up loud audio
        (likely speaker echo from TTS playback), suppress detection to
        avoid self-triggering.
        """
        # Energy gate — compute RMS of frame
        rms = np.sqrt(np.mean(frame.astype(np.float32) ** 2))
        if rms > _ENERGY_GATE_RMS:
            return  # Likely hearing TTS output through mic, suppress

        try:
            prediction = self._stop_model.predict(frame)
        except Exception as e:
            logger.debug("Stop model prediction error: %s", e)
            return

        for model_name, score in prediction.items():
            if score >= self._threshold:
                logger.info("Stop word detected: %s (score=%.3f)", model_name, score)
                self._stop_model.reset()

                if self._on_stop_detect:
                    try:
                        self._on_stop_detect()
                    except Exception as e:
                        logger.error("Stop callback error: %s", e)
