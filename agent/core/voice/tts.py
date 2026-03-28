"""Text-to-speech — Chatterbox (voice clone) with pyttsx3 fallback.

Engine selection:
  ChatterboxEngine — calls http://127.0.0.1:4123/v1/audio/speech (local service)
  Pyttsx3Engine    — Windows SAPI, always available, robotic voice

To use voice cloning:
  1. Run C:\\AI\\chatterbox-api\\_start.bat
  2. Drop a clean 10-30s WAV into C:\\AI\\chatterbox-api\\voice-sample.mp3
  3. TextToSpeech will auto-detect the running service and use it
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import threading

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

try:
    import requests as _requests
except ImportError:
    _requests = None

CHATTERBOX_BASE_PORT = 4123
CHATTERBOX_PORT_RANGE = range(4123, 4130)
_VOICE_SAMPLE = Path(r"C:\AI\chatterbox-api\voice-sample.mp3")
_TMP_DIR = Path(tempfile.gettempdir()) / "roamin_tts"


def _find_chatterbox_url() -> str | None:
    """Scan port range for a running Chatterbox instance. Returns base URL or None."""
    if _requests is None:
        return None
    for port in CHATTERBOX_PORT_RANGE:
        try:
            r = _requests.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            if r.status_code == 200:
                return f"http://127.0.0.1:{port}"
        except Exception:
            continue
    return None


def _chatterbox_available() -> bool:
    """Return True if any Chatterbox instance is reachable."""
    return _find_chatterbox_url() is not None


class TextToSpeech:
    """TTS with automatic engine selection.

    Prefers Chatterbox voice-clone service when running,
    falls back to Windows SAPI (pyttsx3) silently.
    """

    def __init__(self) -> None:
        self._pyttsx3_engine = None
        self._init_pyttsx3()
        _TMP_DIR.mkdir(parents=True, exist_ok=True)

    def _init_pyttsx3(self) -> None:
        if pyttsx3 is None:
            return
        try:
            self._pyttsx3_engine = pyttsx3.init()
            self._pyttsx3_engine.setProperty("rate", 175)
            self._pyttsx3_engine.setProperty("volume", 1.0)
        except Exception as e:
            print(f"[TTS] pyttsx3 init failed: {e}")

    # Pronunciation guide — maps written form to phonetic form that
    # TTS engines render correctly. Case-insensitive replacement applied
    # before every speak() call.
    _PRONUNCIATION: dict[str, str] = {
        "Roamin": "Row-min",
        "roamin": "Row-min",
        "ROAMIN": "Row-min",
    }

    @staticmethod
    def _apply_pronunciation(text: str) -> str:
        """Replace words with phonetic equivalents before synthesis."""
        for written, phonetic in TextToSpeech._PRONUNCIATION.items():
            text = text.replace(written, phonetic)
        return text

    def speak(self, text: str) -> None:
        """Speak text. Uses Chatterbox if available, else pyttsx3."""
        text = self._apply_pronunciation(text)
        if _chatterbox_available():
            self._speak_chatterbox(text)
        else:
            self._speak_pyttsx3(text)

    def _speak_chatterbox(self, text: str) -> None:
        """Send text to Chatterbox API and play the returned audio."""
        if _requests is None:
            self._speak_pyttsx3(text)
            return
        url = _find_chatterbox_url()
        if url is None:
            self._speak_pyttsx3(text)
            return
        try:
            payload: dict = {"input": text, "exaggeration": 0.5, "cfg_weight": 0.5}
            if _VOICE_SAMPLE.exists():
                payload["voice"] = "voice-sample"
            r = _requests.post(f"{url}/v1/audio/speech", json=payload, timeout=30)
            r.raise_for_status()
            out = _TMP_DIR / "chatterbox_out.wav"
            out.write_bytes(r.content)
            self._play_wav(out)
        except Exception as e:
            print(f"[TTS] Chatterbox error: {e} — falling back to pyttsx3")
            self._speak_pyttsx3(text)

    def _speak_pyttsx3(self, text: str) -> None:
        if self._pyttsx3_engine is None:
            print(f"[TTS] (no engine) {text}")
            return
        try:

            def _run() -> None:
                self._pyttsx3_engine.say(text)
                self._pyttsx3_engine.runAndWait()

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join()
        except Exception as e:
            print(f"[TTS] pyttsx3 error: {e}")

    def _play_wav(self, path: Path) -> None:
        """Play a WAV file using winsound (built-in, uses system default device)."""
        try:
            import winsound

            winsound.PlaySound(str(path), winsound.SND_FILENAME)
        except Exception as e:
            print(f"[TTS] playback error: {e}")

    def is_available(self) -> bool:
        """Always True — at minimum pyttsx3 is available."""
        return self._pyttsx3_engine is not None or _chatterbox_available()

    @staticmethod
    def chatterbox_running() -> bool:
        """Return True if Chatterbox is reachable, and print which port."""
        url = _find_chatterbox_url()
        if url:
            print(f"[TTS] Chatterbox found at {url}")
        return url is not None
