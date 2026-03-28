"""Wake listener with hotkey trigger."""

from __future__ import annotations

import re
import threading
import time

try:
    import keyboard
except ImportError:
    keyboard = None

from agent.core.agent_loop import AgentLoop
from agent.core.memory import MemoryManager
from agent.core.model_router import ModelRouter
from agent.core.voice.stt import SpeechToText
from agent.core.voice.tts import TextToSpeech


class WakeListener:
    """Listen for hotkey trigger to activate voice interface."""

    def __init__(self, hotkey: str = "ctrl+space") -> None:
        self._hotkey = hotkey
        self.is_running = False

        if keyboard is None:
            print("[Warning] WakeListener not available (keyboard import failed)")

    @property
    def hotkey(self) -> str:
        """Return the configured hotkey."""
        return self._hotkey

    def start(self) -> None:
        """Start listening for hotkey trigger."""
        if keyboard is None:
            print("[Warning] Cannot start WakeListener - keyboard module unavailable")
            return

        try:
            keyboard.add_hotkey(self._hotkey, self._on_wake_thread)
            self.is_running = True
            print(f"[Roamin] Hotkey listener started: {self._hotkey}")
        except Exception as e:
            print(f"[Warning] Failed to register hotkey: {e}")

    def stop(self) -> None:
        """Stop listening for hotkey trigger."""
        if keyboard is None:
            return

        try:
            keyboard.remove_hotkey(self._hotkey)
            self.is_running = False
            print("[Roamin] Hotkey listener stopped")
        except Exception as e:
            print(f"[Warning] Failed to unregister hotkey: {e}")

    def _on_wake_thread(self) -> None:
        """Call _on_wake in a new thread (non-blocking)."""
        thread = threading.Thread(target=self._on_wake, daemon=True)
        thread.start()

    def _on_wake(self) -> None:
        """Handle wake word trigger: listen for command and execute."""
        t0 = time.perf_counter()
        print("[Roamin] Wake triggered at t=0.000")

        # Greet user
        tts = TextToSpeech()
        if tts.is_available():
            tts.speak("Yes?")
        t_greeted = time.perf_counter()
        print(f"[Roamin] t={t_greeted - t0:.3f}s  'Yes?' spoken")

        # STT — record and transcribe
        stt = SpeechToText()
        transcription = None
        try:
            transcription = stt.record_and_transcribe(duration_seconds=5)
        except Exception as e:
            print(f"[Warning] STT error: {e}")
        t_stt = time.perf_counter()
        print(f"[Roamin] t={t_stt - t0:.3f}s  STT done (+{t_stt - t_greeted:.3f}s) → '{transcription}'")

        if transcription is None or transcription.strip() == "":
            if tts.is_available():
                tts.speak("Sorry, I didn't catch that.")
            return

        # AgentLoop
        result = {}
        try:
            agent_loop = AgentLoop()
            result = agent_loop.run(transcription)
        except Exception as e:
            print(f"[Warning] AgentLoop error: {e}")
            if tts.is_available():
                tts.speak("I encountered an error processing that command.")
            return
        t_agent = time.perf_counter()
        print(f"[Roamin] t={t_agent - t0:.3f}s  AgentLoop done (+{t_agent - t_stt:.3f}s) status={result.get('status')}")

        # Generate reply via ModelRouter
        reply = "Done."
        status = result.get("status", "unknown")
        if status == "completed":
            try:
                router = ModelRouter()
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are Roamin, a voice assistant. "
                            "Reply in ONE short sentence, spoken naturally. "
                            "No narration, no lists, no internal state. "
                            "Just a direct natural reply."
                        ),
                    },
                    {"role": "user", "content": transcription},
                ]
                reply = router.respond(
                    "default",
                    transcription,
                    messages=messages,
                    max_tokens=60,
                    temperature=0.7,
                    no_think=True,
                )
                reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
                reply = reply[:200] if reply else "Done."
            except Exception:
                reply = "Done."
        elif status == "failed":
            reply = "I couldn't complete that task."
        elif status == "blocked":
            reply = "That action needs your approval."
        else:
            reply = "Working on it."
        t_reply = time.perf_counter()
        print(f"[Roamin] t={t_reply - t0:.3f}s  Reply generated (+{t_reply - t_agent:.3f}s) → '{reply}'")

        # TTS — speak reply
        if tts.is_available():
            tts.speak(reply)
        t_spoken = time.perf_counter()
        print(f"[Roamin] t={t_spoken - t0:.3f}s  Reply spoken (+{t_spoken - t_reply:.3f}s)")
        print(f"[Roamin] TOTAL: {t_spoken - t0:.3f}s")

        # Store in memory
        try:
            memory = MemoryManager()
            memory.write_to_memory(
                "conversation",
                {"session_id": "voice_interface", "model_used": "whisper", "content": f"User: {transcription}"},
            )
        except Exception:
            pass
