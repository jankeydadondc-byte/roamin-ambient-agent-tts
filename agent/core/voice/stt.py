"""Speech-to-text using openai-whisper."""

from __future__ import annotations

import threading
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

    # Whisper initial_prompt primes the decoder with proper nouns so it biases
    # toward correct spellings instead of phonetic guesses like "A Roman".
    # Keep it SHORT — a long prompt causes Whisper to hallucinate the prompt
    # text verbatim when audio is quiet or ambiguous.
    _INITIAL_PROMPT = "Roamin, Asherre, MemPalace."

    def __init__(self, model_name: str = "base") -> None:
        self._model = None
        self._vad_model = None

        if whisper is None:
            print("[Warning] SpeechToText not available (whisper import failed)")
            return

        # Load Whisper model ONCE at init - using base model for reasonable accuracy/speed
        # Prefer CUDA if available (20x faster than CPU FP32)
        try:
            # Determine device: CUDA if available and torch imported, else CPU
            device = "cuda" if (_silero_available and torch.cuda.is_available()) else "cpu"
            self._model = whisper.load_model(model_name, device=device)
            print(f"[Roamin] Whisper loaded on {device.upper()}")
        except Exception as e:
            print(f"[Warning] Failed to load Whisper model: {e}")

        # Load Silero VAD model once if available
        if _silero_available and self._model is not None:
            try:
                self._vad_model = load_silero_vad()
            except Exception as e:
                print(f"[Warning] Failed to load Silero VAD model: {e}")
                self._vad_model = None

    def record_and_transcribe(
        self,
        duration_seconds: int = 5,
        stop_event: threading.Event | None = None,
    ) -> str | None:
        """
        Record audio and transcribe using Whisper.

        With Silero VAD: detects end-of-speech via silence detection.
        Fallback: records fixed duration as float32 if VAD unavailable.

        Args:
            duration_seconds: Duration of fallback recording (default 5 seconds)
            stop_event: If set, recording is abandoned and None is returned.

        Returns:
            Transcribed text or None on failure
        """
        if sd is None or self._model is None:
            print("[Warning] SpeechToText not available")
            return None

        # Fallback to fixed-duration recording if Silero VAD not available
        if self._vad_model is None:
            return self._record_fixed(duration_seconds, stop_event=stop_event)

        sample_rate = 16000
        chunk_size = 512  # samples per chunk (~32ms at 16kHz)

        try:
            audio_buffer = []
            silence_chunks = 0
            speech_confirm_chunks = 0
            speech_started = False
            total_chunks = 0
            chunks_since_speech_started = 0  # wall-clock chunks elapsed since speech_started=True
            done_event = threading.Event()

            print("[Roamin] Listening (Silero VAD)...")

            def callback(indata, frames, time_status, buffer):
                nonlocal silence_chunks, speech_started, speech_confirm_chunks
                nonlocal total_chunks, chunks_since_speech_started

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
                            done_event.set()
                            raise sd.CallbackStop()
                else:
                    # Speech already started, watch for silence.
                    # Guard: don't allow silence to end recording until at least 15 wall-clock
                    # chunks (~480ms) have elapsed since speech_started. This uses total elapsed
                    # time rather than VAD-probability-weighted chunks, so short phrases like
                    # "What time is it?" still fire normally — they produce 47+ total chunks
                    # before silence. A single-syllable "hey" produces only ~6 chunks before
                    # the user pauses, so the gate stays closed through the pause.
                    chunks_since_speech_started += 1
                    if prob >= 0.3:
                        silence_chunks = 0
                    elif chunks_since_speech_started >= 15:
                        silence_chunks += 1
                        if silence_chunks >= 24:  # ~768ms of silence after sufficient speech
                            done_event.set()
                            raise sd.CallbackStop()

                # Safety cap: max 10 seconds total recording
                if total_chunks > 3200:
                    done_event.set()
                    raise sd.CallbackStop()

            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=chunk_size,
                callback=callback,
            ):
                # Poll at 50ms intervals so stop_event can interrupt recording.
                # done_event fires via VAD callback (CallbackStop); deadline is safety wall.
                deadline = time.monotonic() + 12
                while not done_event.is_set():
                    if stop_event is not None and stop_event.is_set():
                        done_event.set()
                        break
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.05)

        except sd.CallbackStop:
            pass  # Normal termination via VAD logic
        except Exception as e:
            print(f"[Warning] STT recording failed: {e}")
            return None

        if not audio_buffer:
            return None

        # Skip Whisper if stop fired during recording — discard captured audio
        if stop_event is not None and stop_event.is_set():
            return None

        try:
            audio = np.concatenate(audio_buffer).astype("float32")

            result = self._model.transcribe(
                audio,
                language="en",
                initial_prompt=self._INITIAL_PROMPT,
                temperature=0.0,  # greedy decode — suppresses hallucinated words
                no_speech_threshold=0.6,  # raise threshold to reject silence
            )
            text = result.get("text", "").strip()

            return text if text else None

        except Exception as e:
            print(f"[Warning] STT transcription failed: {e}")
            return None

    def _record_fixed(
        self,
        duration_seconds: int = 5,
        stop_event: threading.Event | None = None,
    ) -> str | None:
        """Fallback fixed-duration recording for when Silero VAD is unavailable."""
        if sd is None or self._model is None:
            return None
        sample_rate = 16000
        try:
            print(f"[Roamin] Listening for {duration_seconds} seconds (fallback mode)...")
            recording = sd.rec(int(duration_seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")

            if stop_event is not None:

                def _watchdog() -> None:
                    # Bounded — expires naturally when recording ends. No thread leak.
                    stop_event.wait(timeout=duration_seconds + 2)
                    if stop_event.is_set():
                        try:
                            sd.stop()  # safe on idle device — no exception
                        except Exception:
                            pass

                threading.Thread(target=_watchdog, daemon=True, name="stt-stop-watchdog").start()

            sd.wait()

            audio = recording.flatten()
            result = self._model.transcribe(
                audio,
                language="en",
                initial_prompt=self._INITIAL_PROMPT,
                temperature=0.0,
                no_speech_threshold=0.6,
            )
            text = result.get("text", "").strip()

            return text if text else None

        except Exception as e:
            print(f"[Warning] STT failed: {e}")
            return None

    def is_available(self) -> bool:
        """Check if STT engine is available."""
        return self._model is not None and whisper is not None
