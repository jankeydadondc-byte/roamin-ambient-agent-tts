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

    def __init__(
        self,
        hotkey: str = "ctrl+space",
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        agent_loop: AgentLoop | None = None,
    ) -> None:
        self._hotkey = hotkey
        self.is_running = False
        # Use pre-loaded instances if provided, else lazy-load on first wake
        self._stt = stt
        self._tts = tts
        self._agent_loop = agent_loop

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

    def _extract_and_store_fact(self, transcription: str, memory: MemoryManager) -> bool:
        """Detect 'remember X is Y' patterns and store as named_fact. Returns True if fact stored."""
        lower = transcription.lower()
        patterns = [
            r"remember (?:that )?my (.+?) is (.+)",
            r"my (.+?) is (.+)",
            r"save (?:that )?my (.+?) is (.+)",
            r"note (?:that )?my (.+?) is (.+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, lower)
            if m:
                fact_name = m.group(1).strip().rstrip(".")
                fact_value = m.group(2).strip().rstrip(".")
                try:
                    memory.write_to_memory("named_fact", {"fact_name": fact_name, "value": fact_value})
                    print(f"[Roamin] Stored fact: '{fact_name}' = '{fact_value}'")
                    return True
                except Exception as e:
                    print(f"[Warning] Failed to store fact: {e}")
        return False

    def _build_memory_context(self, transcription: str, memory: MemoryManager) -> str:
        """Query memory and build a context string to inject into the reply prompt."""
        context_parts = []

        # Search ChromaDB for semantically related memories
        try:
            results = memory.search_memory(transcription)
            docs = results.get("documents", [])
            if docs:
                context_parts.append("Relevant memories: " + " | ".join(docs[:3]))
        except Exception:
            pass

        # Pull all named facts (small table, load all)
        try:
            from agent.core.memory.memory_store import MemoryStore

            store = MemoryStore()
            facts = store.get_all_named_facts() if hasattr(store, "get_all_named_facts") else []
            if facts:
                fact_strs = [f"{f['fact_name']}: {f['value']}" for f in facts]
                context_parts.append("Known facts about the user: " + ", ".join(fact_strs))
        except Exception:
            pass

        return "\n".join(context_parts)

    def _on_wake(self) -> None:
        """Handle wake word trigger: listen for command and execute."""
        t0 = time.perf_counter()
        print("[Roamin] Wake triggered at t=0.000")

        # Use pre-loaded instances or lazy-load if not provided
        tts = self._tts or TextToSpeech()
        stt = self._stt or SpeechToText()
        agent_loop = self._agent_loop or AgentLoop()

        # Greet user
        if tts.is_available():
            tts.speak("yes? how can i help you")
        t_greeted = time.perf_counter()
        print(f"[Roamin] t={t_greeted - t0:.3f}s  'Yes?' spoken")

        # STT — record and transcribe
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

        # Memory — extract facts and build context before AgentLoop
        memory = MemoryManager()
        fact_stored = self._extract_and_store_fact(transcription, memory)
        memory_context = self._build_memory_context(transcription, memory)

        # AgentLoop
        result = {}
        try:
            result = agent_loop.run(transcription)
        except Exception as e:
            print(f"[Warning] AgentLoop error: {e}")
            if tts.is_available():
                tts.speak("I encountered an error processing that command.")
            return
        t_agent = time.perf_counter()
        print(f"[Roamin] t={t_agent - t0:.3f}s  AgentLoop done (+{t_agent - t_stt:.3f}s) status={result.get('status')}")

        # Generate reply with memory context injected
        reply = "Got it." if fact_stored else "Done."
        status = result.get("status", "unknown")
        if status == "completed":
            try:
                router = ModelRouter()
                system_content = (
                    "You are Roamin, a voice assistant. "
                    "Reply in ONE short sentence, spoken naturally. "
                    "No narration, no lists, no internal state. "
                    "Just a direct natural reply."
                )
                if memory_context:
                    system_content += f"\n\n{memory_context}"
                messages = [
                    {"role": "system", "content": system_content},
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
                reply = reply[:200] if reply else ("Got it." if fact_stored else "Done.")
            except Exception:
                reply = "Got it." if fact_stored else "Done."
        elif status == "failed":
            reply = "I couldn't complete that task."
        elif status == "blocked":
            reply = "That action needs your approval."
        t_reply = time.perf_counter()
        print(f"[Roamin] t={t_reply - t0:.3f}s  Reply generated (+{t_reply - t_agent:.3f}s) → '{reply}'")

        # TTS — speak reply
        if tts.is_available():
            tts.speak(reply)
        t_spoken = time.perf_counter()
        print(f"[Roamin] t={t_spoken - t0:.3f}s  Reply spoken (+{t_spoken - t_reply:.3f}s)")
        print(f"[Roamin] TOTAL: {t_spoken - t0:.3f}s")

        # Store conversation in memory
        try:
            memory.write_to_memory(
                "conversation",
                {"session_id": "voice_interface", "model_used": "whisper", "content": f"User: {transcription}"},
            )
        except Exception:
            pass
