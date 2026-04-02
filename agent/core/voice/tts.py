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

import hashlib
import tempfile
from pathlib import Path

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
_CACHE_DIR = Path(__file__).parent / "phrase_cache"

# Pre-defined phrases to cache as WAV files at startup.
# Speak these instantly without hitting Chatterbox API.
CACHED_PHRASES: list[str] = [
    "yes? how can i help you",
    "Done.",
    "Sorry, I didn't catch that.",
    "Working on it.",
    "The agent loop failed to complete that task.",
    "That action needs your approval.",
    "Got it.",
    "I ran into an unexpected error, something fucked up while processing that.",
    "On it.",
    "I'm not sure about that one.",
    "Give me a second.",
    "Anything else?",
    "I didn't find anything about that.",
]

# Per-phrase synthesis overrides — tune exaggeration/cfg_weight per phrase
# Default: exaggeration=0.5, cfg_weight=0.5
PHRASE_PARAMS: dict[str, dict] = {
    "yes? how can i help you": {"exaggeration": 0.6, "cfg_weight": 0.4},
    "On it.": {"exaggeration": 0.6, "cfg_weight": 0.4},
    "Got it.": {"exaggeration": 0.6, "cfg_weight": 0.4},
}


def _phrase_cache_key(text: str) -> str:
    """Generate a safe filename key for a cached phrase."""
    return hashlib.md5(text.encode()).hexdigest() + ".wav"


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


def _synthesize_to_file(text: str, url: str, dest: Path, exaggeration: float = 0.5, cfg_weight: float = 0.5) -> bool:
    """Synthesize text via Chatterbox and save WAV to dest. Returns True on success."""
    if _requests is None:
        return False
    for attempt in range(2):
        try:
            payload: dict = {"input": text, "exaggeration": exaggeration, "cfg_weight": cfg_weight}
            if _VOICE_SAMPLE.exists():
                payload["voice"] = "voice-sample"
            timeout = min(15 + len(text) // 10, 25)
            r = _requests.post(f"{url}/v1/audio/speech", json=payload, timeout=timeout)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return True
        except Exception as e:
            if attempt == 0:
                print(f"[TTS] Synthesis attempt 1 failed for '{text[:30]}': {e} — retrying...")
            else:
                print(f"[TTS] Synthesis failed after retry for '{text[:30]}': {e}")
    return False


class TextToSpeech:
    """TTS with automatic engine selection and phrase cache.

    Prefers cached WAV files for known phrases (instant playback),
    then Chatterbox for novel text, then pyttsx3 as final fallback.
    """

    def __init__(self) -> None:
        self._pyttsx3_engine = None
        self._phrase_cache: dict[str, Path] = {}  # text -> WAV path
        self._init_pyttsx3()
        _TMP_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _init_pyttsx3(self) -> None:
        if pyttsx3 is None:
            return
        try:
            self._pyttsx3_engine = pyttsx3.init()
            self._pyttsx3_engine.setProperty("rate", 175)
            self._pyttsx3_engine.setProperty("volume", 1.0)
        except Exception as e:
            print(f"[TTS] pyttsx3 init failed: {e}")

    def warm_phrase_cache(self) -> None:
        """Pre-generate all CACHED_PHRASES as WAV files. Call at startup."""
        url = _find_chatterbox_url()
        if url is None:
            print("[TTS] Chatterbox not available — phrase cache skipped")
            return

        generated = 0
        skipped = 0
        for phrase in CACHED_PHRASES:
            key = _phrase_cache_key(phrase)
            dest = _CACHE_DIR / key
            if dest.exists() and dest.stat().st_size > 0:
                # Already cached — just register it
                self._phrase_cache[phrase] = dest
                skipped += 1
            else:
                print(f"[TTS] Caching: '{phrase}'")
                params = PHRASE_PARAMS.get(phrase, {})
                if _synthesize_to_file(phrase, url, dest, **params):
                    self._phrase_cache[phrase] = dest
                    generated += 1
        print(f"[TTS] Phrase cache ready: {generated} generated, {skipped} loaded from disk")

    # Pronunciation guide
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
        """Speak text. Uses cached WAV if available, then Chatterbox, then pyttsx3."""
        text = self._apply_pronunciation(text)

        # Check phrase cache first — instant playback
        if text in self._phrase_cache:
            wav = self._phrase_cache[text]
            if wav.exists():
                print(f"[TTS] Cache hit: '{text}'")
                self._play_wav(wav)
                return

        # Fall through to live synthesis
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
            out = _TMP_DIR / "chatterbox_out.wav"
            if _synthesize_to_file(text, url, out):
                self._play_wav(out)
            else:
                print("[TTS] Chatterbox synthesis failed — falling back to SAPI")
                self._speak_pyttsx3(text)
        except Exception as e:
            print(f"[TTS] Chatterbox error: {e} — falling back to SAPI")
            self._speak_pyttsx3(text)

    def _speak_sapi_subprocess(self, text: str) -> None:
        """Speak via Windows SAPI using PowerShell — works from any thread, no COM affinity."""
        import subprocess

        safe = text.replace("'", "''")  # escape single quotes for PowerShell
        try:
            subprocess.run(
                [
                    "powershell",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    (
                        "Add-Type -AssemblyName System.Speech; "
                        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                        f"$s.Speak('{safe}')"
                    ),
                ],
                timeout=30,
                check=False,
            )
        except Exception as e:
            print(f"[TTS] SAPI fallback error: {e}")

    def _speak_pyttsx3(self, text: str) -> None:
        import threading

        if threading.current_thread() is not threading.main_thread():
            # pyttsx3 COM calls deadlock outside the main thread on Windows — use SAPI instead
            self._speak_sapi_subprocess(text)
            return
        if self._pyttsx3_engine is None:
            self._speak_sapi_subprocess(text)
            return
        try:
            self._pyttsx3_engine.say(text)
            self._pyttsx3_engine.runAndWait()
        except Exception as e:
            print(f"[TTS] pyttsx3 error: {e}")
            self._speak_sapi_subprocess(text)

    def _play_wav(self, path: Path) -> None:
        """Play a WAV file using winsound."""
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
