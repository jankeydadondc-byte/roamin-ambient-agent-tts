"""Speech-to-text using openai-whisper."""

from __future__ import annotations

import time

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    import whisper
except ImportError:
    whisper = None

try:
    import torch
    from silero_vad import load_silero_vad

    _silero_available = True
except ImportError:
    _silero_available = False


class SpeechToText:
    """STT engine using Whisper for transcription."""

    def __init__(self, model_name: str = "base") -> None:
        self._model = None
        self._vad_model = None

        if whisper is None:
            print("[Warning] SpeechToText not available (whisper import failed)")
            return

        # Load Whisper model ONCE at init - using base model for reasonable accuracy/speed
        try:
            self._model = whisper.load_model(model_name)
        except Exception as e:
            print(f"[Warning] Failed to load Whisper model: {e}")

        # Load Silero VAD model once if available
        if _silero_available and self._model is not None:
            try:
                self._vad_model = load_silero_vad()
            except Exception as e:
                print(f"[Warning] Failed to load Silero VAD model: {e}")
                self._vad_model = None

    def record_and_transcribe(self, duration_seconds: int = 5) -> str | None:
        """
        Record audio and transcribe using Whisper.

        With Silero VAD: detects end-of-speech via silence detection.
        Fallback: records fixed duration as float32 if VAD unavailable.

        Args:
            duration_seconds: Duration of fallback recording (default 5 seconds)

        Returns:
            Transcribed text or None on failure
        """
        if sd is None or self._model is None:
            print("[Warning] SpeechToText not available")
            return None

        # Fallback to fixed-duration recording if Silero VAD not available
        if self._vad_model is None:
            return self._record_fixed(duration_seconds)

        sample_rate = 16000
        chunk_size = 512  # samples per chunk (~32ms at 16kHz)

        try:
            audio_buffer = []
            silence_chunks = 0
            speech_confirm_chunks = 0
            speech_started = False
            total_chunks = 0

            print("[Roamin] Listening (Silero VAD)...")

            def callback(indata, frames, time_status, buffer):
                nonlocal silence_chunks, speech_started, speech_confirm_chunks, total_chunks

                if frames != chunk_size:
                    return

                # Extract mono channel as float32 numpy array
                chunk = indata[:, 0].astype("float32")
                audio_buffer.append(chunk.copy())

                # Run Silero VAD on this chunk
                chunk_tensor = torch.from_numpy(chunk).float()
                prob = self._vad_model(chunk_tensor, sample_rate).item()

                total_chunks += 1

                # State machine logic
                if not speech_started:
                    if prob > 0.5:
                        speech_confirm_chunks += 1
                        if speech_confirm_chunks >= 2:
                            speech_started = True
                            silence_chunks = 0
                    else:
                        speech_confirm_chunks = 0
                        if total_chunks > 800:  # 5 second timeout with no speech
                            raise sd.CallbackStop()
                else:
                    # Speech already started, watch for silence
                    if prob < 0.3:
                        silence_chunks += 1
                        if silence_chunks >= 24:  # 24 chunks = ~1.5 seconds of silence
                            raise sd.CallbackStop()
                    else:
                        silence_chunks = 0

                # Safety cap: max 10 seconds total recording
                if total_chunks > 3200:
                    raise sd.CallbackStop()

            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=chunk_size,
                callback=callback,
            ):
                while True:
                    time.sleep(0.1)

        except sd.CallbackStop:
            pass  # Normal termination via VAD logic
        except Exception as e:
            print(f"[Warning] STT recording failed: {e}")
            return None

        if not audio_buffer:
            return None

        try:
            audio = np.concatenate(audio_buffer).astype("float32")

            result = self._model.transcribe(audio)
            text = result.get("text", "").strip()

            return text if text else None

        except Exception as e:
            print(f"[Warning] STT transcription failed: {e}")
            return None

    def _record_fixed(self, duration_seconds: int = 5) -> str | None:
        """Fallback fixed-duration recording for when Silero VAD is unavailable."""
        if sd is None or self._model is None:
            return None
        sample_rate = 16000
        try:
            print(f"[Roamin] Listening for {duration_seconds} seconds (fallback mode)...")
            recording = sd.rec(int(duration_seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
            sd.wait()

            audio = recording.flatten()
            result = self._model.transcribe(audio)
            text = result.get("text", "").strip()

            return text if text else None

        except Exception as e:
            print(f"[Warning] STT failed: {e}")
            return None

    def is_available(self) -> bool:
        """Check if STT engine is available."""
        return self._model is not None and whisper is not None
