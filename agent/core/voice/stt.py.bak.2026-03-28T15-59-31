"""Speech-to-text using openai-whisper."""

from __future__ import annotations

from pathlib import Path

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    import whisper
except ImportError:
    whisper = None


class SpeechToText:
    """STT engine using Whisper for transcription."""

    def __init__(self, model_name: str = "base") -> None:
        self._model = None

        if whisper is None:
            print("[Warning] SpeechToText not available (whisper import failed)")
            return

        # Load model ONCE at init - using base model for reasonable accuracy/speed
        try:
            self._model = whisper.load_model(model_name)
        except Exception as e:
            print(f"[Warning] Failed to load Whisper model: {e}")

    def record_and_transcribe(self, duration_seconds: int = 5) -> str | None:
        """
        Record audio and transcribe using Whisper.

        Records at 16000Hz sample rate for duration_seconds.
        Saves to temp file and transcribes.

        Args:
            duration_seconds: Duration of recording (default 5 seconds)

        Returns:
            Transcribed text or None on failure
        """
        if sd is None or self._model is None:
            print("[Warning] SpeechToText not available")
            return None

        sample_rate = 16000

        try:
            # Record audio
            print(f"[Roamin] Listening for {duration_seconds} seconds...")
            recording = sd.rec(int(duration_seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="int16")
            sd.wait()  # Wait for recording to complete

            # Save to temporary WAV file
            temp_dir = Path(__file__).parent / "tmp"
            temp_dir.mkdir(exist_ok=True)
            temp_file = temp_dir / "recording.wav"

            import wave

            import numpy as np

            with wave.open(str(temp_file), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(recording.astype(np.int16).tobytes())

            # Transcribe with Whisper
            result = self._model.transcribe(str(temp_file))
            text = result.get("text", "").strip()

            return text if text else None

        except Exception as e:
            print(f"[Warning] STT failed: {e}")
            return None

    def is_available(self) -> bool:
        """Check if STT engine is available."""
        return self._model is not None and whisper is not None
