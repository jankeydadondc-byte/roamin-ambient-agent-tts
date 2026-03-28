"""Wake listener with hotkey trigger."""

from __future__ import annotations

import re
import threading

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
        print("[Roamin] Wake word triggered")

        # Greet user
        tts = TextToSpeech()
        if tts.is_available():
            tts.speak("Yes?")

        # Listen for command
        stt = SpeechToText()
        transcription = None

        try:
            transcription = stt.record_and_transcribe(duration_seconds=5)
        except Exception as e:
            print(f"[Warning] STT error: {e}")

        if transcription is None or transcription.strip() == "":
            if tts.is_available():
                tts.speak("Sorry, I didn't catch that.")
            return

        print(f"[Roamin] Command: {transcription}")

        # Execute command
        try:
            agent_loop = AgentLoop()
            result = agent_loop.run(transcription)

            # Reply based on result
            if tts.is_available():
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
                        )
                        # Strip reasoning tokens and clean up
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

                tts.speak(reply)
        except Exception as e:
            print(f"[Warning] AgentLoop error: {e}")
            if tts.is_available():
                tts.speak("I encountered an error processing that command.")

        # Store interaction in memory
        try:
            memory = MemoryManager()
            memory.write_to_memory(
                "conversation",
                {"session_id": "voice_interface", "model_used": "whisper", "content": f"User: {transcription}"},
            )
        except Exception:
            pass  # Non-critical - don't fail if memory storage fails
