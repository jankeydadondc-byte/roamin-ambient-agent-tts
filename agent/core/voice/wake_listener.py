"""Wake listener with hotkey trigger."""

from __future__ import annotations

import base64
import io
import re
import sys
import threading
import time
import traceback

try:
    import keyboard
except ImportError:
    keyboard = None

from agent.core.agent_loop import AgentLoop
from agent.core.memory import MemoryManager
from agent.core.model_router import ModelRouter
from agent.core.tool_registry import ToolRegistry
from agent.core.voice.stt import SpeechToText
from agent.core.voice.tts import TextToSpeech


def _classify_think_level(text: str) -> tuple[bool, int]:
    """Classify how much thinking Roamin should do for this prompt.

    Returns:
        (no_think: bool, max_tokens: int)
        OFF  (no_think=True,  max_tokens=60)   — default, simple queries
        LOW  (no_think=False, max_tokens=512)  — basic think triggers
        MED  (no_think=False, max_tokens=2048) — explicit think hard requests
        HIGH (no_think=False, max_tokens=8192) — max effort requests
    """
    lower = text.lower()

    high_triggers = [
        "max thinking",
        "max effort",
        "think really hard",
        "this is important",
        "don't mess this up",
        "dont mess this up",
        "don't fuck this up",
        "dont fuck this up",
        "give it everything",
        "full effort",
    ]
    if any(t in lower for t in high_triggers):
        return False, 8192

    med_triggers = [
        "really think",
        "think hard",
        "think carefully",
        "think through carefully",
        "think deeply",
        "take your time",
        "be thorough",
    ]
    if any(t in lower for t in med_triggers):
        return False, 2048

    low_triggers = [
        "think about",
        "think through",
        "analyze",
        "analyse",
        "explain why",
        "explain how",
        "reason through",
        "figure out",
        "what do you think",
        "help me decide",
        "compare",
        "pros and cons",
        "difference between",
        "how does",
        "why does",
        "why is",
        "why are",
        "what would",
        "what if",
    ]
    if any(t in lower for t in low_triggers):
        return False, 512

    return True, 60


def _try_direct_dispatch(transcription: str, registry: ToolRegistry) -> dict | None:
    """Match transcription to a tool directly, bypassing the AgentLoop planner.

    Returns tool result dict if matched, None to fall through to AgentLoop.
    """
    lower = transcription.lower()

    # --- Web search ---
    for trigger in ["search for ", "look up ", "google ", "find out about ", "find out "]:
        if trigger in lower:
            idx = lower.index(trigger) + len(trigger)
            query = transcription[idx:].strip().rstrip(".?!")
            if query:
                print(f"[Roamin] Direct dispatch: web_search('{query}')")
                return registry.execute("web_search", {"query": query})

    # Queries that imply web search (current events, news, weather)
    news_patterns = [
        r"(?:what|anything).*(?:happen|going on|news).*(?:in |today|tonight|yesterday)",
        r"(?:how'?s|what'?s).*(?:weather|temperature)",
    ]
    for pattern in news_patterns:
        m = re.search(pattern, lower)
        if m:
            print(f"[Roamin] Direct dispatch: web_search('{transcription}')")
            return registry.execute("web_search", {"query": transcription})

    # --- Screen observation ---
    screen_triggers = [
        "what's on my screen",
        "what is on my screen",
        "what am i looking at",
        "what do you see",
        "what's on screen",
        "describe my screen",
        "look at my screen",
        "what am i doing",
    ]
    if any(t in lower for t in screen_triggers):
        print("[Roamin] Direct dispatch: take_screenshot()")
        return registry.execute("take_screenshot", {})

    # --- Clipboard ---
    if "clipboard" in lower:
        if any(w in lower for w in ["read", "what's in", "what is in", "paste", "show"]):
            print("[Roamin] Direct dispatch: clipboard_read()")
            return registry.execute("clipboard_read", {})
        # "copy X to clipboard"
        m = re.search(r"copy (.+?) to (?:my )?clipboard", lower)
        if m:
            text = m.group(1).strip()
            print(f"[Roamin] Direct dispatch: clipboard_write('{text[:50]}')")
            return registry.execute("clipboard_write", {"text": text})

    # --- Open URL ---
    url_match = re.search(r"open\s+(https?://\S+)", lower)
    if url_match:
        url = url_match.group(1)
        print(f"[Roamin] Direct dispatch: open_url('{url}')")
        return registry.execute("open_url", {"url": url})

    # --- Memory recall ---
    fact_match = re.search(r"what(?:'s| is) my (.+?)[\?\.]?$", lower)
    if fact_match:
        fact_name = fact_match.group(1).strip()
        print(f"[Roamin] Direct dispatch: memory_recall('{fact_name}')")
        return registry.execute("memory_recall", {"fact_name": fact_name})

    # --- Git ---
    if "git status" in lower:
        print("[Roamin] Direct dispatch: git_status()")
        return registry.execute("git_status", {})
    if "git diff" in lower:
        print("[Roamin] Direct dispatch: git_diff()")
        return registry.execute("git_diff", {})
    if "git log" in lower:
        print("[Roamin] Direct dispatch: git_log()")
        return registry.execute("git_log", {"n": 10})

    # --- Port check ---
    port_match = re.search(r"(?:check |is ).*(?:port |running).*?(\d{2,5})", lower)
    if port_match:
        port = int(port_match.group(1))
        print(f"[Roamin] Direct dispatch: check_port({port})")
        return registry.execute("check_port", {"port": port})
    # "is chatterbox running" → port 4123
    if any(w in lower for w in ["chatterbox running", "chatterbox up", "chatterbox online"]):
        print("[Roamin] Direct dispatch: check_port(4123)")
        return registry.execute("check_port", {"port": 4123})

    # --- Process list ---
    if any(t in lower for t in ["list processes", "what's running", "running processes", "task list"]):
        print("[Roamin] Direct dispatch: list_processes()")
        return registry.execute("list_processes", {})

    return None


class WakeListener:

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
        self._wake_lock = threading.Lock()

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
        """Call _on_wake in a new thread (non-blocking). Drops if already running."""
        if not self._wake_lock.acquire(blocking=False):
            print("[Roamin] Wake already in progress, ignoring")
            return

        def _guarded_wake():
            try:
                self._on_wake()
            except Exception as e:
                print(f"[Roamin] FATAL in _on_wake: {e}", flush=True)
                traceback.print_exc()
                sys.stdout.flush()
                sys.stderr.flush()
            finally:
                self._wake_lock.release()

        thread = threading.Thread(target=_guarded_wake, daemon=False)
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

        # Pull all named facts — only inject ones relevant to this query
        facts = []
        try:
            from agent.core.memory.memory_store import MemoryStore

            store = MemoryStore()
            facts = store.get_all_named_facts() if hasattr(store, "get_all_named_facts") else []
        except Exception:
            pass
        if facts:
            lower_query = transcription.lower()
            relevant = [f for f in facts if f["fact_name"].lower() in lower_query]
            if relevant:
                fact_strs = [f"{f['fact_name']}: {f['value']}" for f in relevant]
                context_parts.append("Known facts about the user: " + ", ".join(fact_strs))

        return "\n".join(context_parts)

    def _on_wake(self) -> None:
        """Handle wake word trigger: listen for command and execute."""
        t0 = time.perf_counter()
        print("[Roamin] Wake triggered at t=0.000", flush=True)

        # Use pre-loaded instances or lazy-load if not provided
        tts = self._tts or TextToSpeech()
        stt = self._stt or SpeechToText()
        agent_loop = self._agent_loop or AgentLoop()

        # Greet user
        if tts.is_available():
            tts.speak("yes? how can i help you")
        t_greeted = time.perf_counter()
        print(f"[Roamin] t={t_greeted - t0:.3f}s  'Yes?' spoken", flush=True)

        # STT — record and transcribe
        transcription = None
        try:
            transcription = stt.record_and_transcribe(duration_seconds=5)
        except Exception as e:
            print(f"[Warning] STT error: {e}", flush=True)
        t_stt = time.perf_counter()
        print(f"[Roamin] t={t_stt - t0:.3f}s  STT done (+{t_stt - t_greeted:.3f}s) → '{transcription}'", flush=True)

        if transcription is None or transcription.strip() == "":
            if tts.is_available():
                tts.speak("Sorry, I didn't catch that.")
            return

        # Memory — extract facts and build context before AgentLoop
        memory = MemoryManager()
        fact_stored = self._extract_and_store_fact(transcription, memory)
        memory_context = self._build_memory_context(transcription, memory)

        # Layer 1: Direct tool dispatch — pattern match to skip AgentLoop
        registry = ToolRegistry()
        direct_result = _try_direct_dispatch(transcription, registry)
        t_dispatch = time.perf_counter()

        tool_context = ""
        if direct_result is not None and direct_result.get("success"):
            print(f"[Roamin] t={t_dispatch - t0:.3f}s  Direct dispatch (+{t_dispatch - t_stt:.3f}s)")

            # Vision fast-path — screenshot_path present means image bytes must reach the LLM
            screenshot_path = direct_result.get("screenshot_path")
            if screenshot_path:
                try:
                    from PIL import Image

                    # Load and resize to max 1024x1024 (mmproj re-encodes anyway; keeps base64 small)
                    img = Image.open(screenshot_path)
                    img.thumbnail((1024, 1024), Image.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

                    vision_messages = [
                        {
                            "role": "system",
                            "content": (
                                "You are Roamin, a voice assistant. "
                                "The user has shared their screen. "
                                "Describe what you see in ONE short spoken sentence. "
                                "No lists, no markdown."
                            ),
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": transcription},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                                },
                            ],
                        },
                    ]
                    vision_router = ModelRouter()
                    vision_reply = vision_router.respond(
                        "vision",
                        transcription,
                        messages=vision_messages,  # type: ignore[arg-type]
                        max_tokens=150,
                        temperature=0.7,
                        no_think=True,
                    )
                    vision_reply = re.sub(r"<think>.*?</think>", "", vision_reply, flags=re.DOTALL).strip()
                    vision_reply = re.sub(r"[^\x00-\x7F]+", "", vision_reply).strip()
                    vision_reply = vision_reply[:200] if vision_reply else "I can see your screen."
                    t_reply = time.perf_counter()
                    print(
                        f"[Roamin] t={t_reply - t0:.3f}s  Reply generated "
                        f"(+{t_reply - t_dispatch:.3f}s) \u2192 '{vision_reply}'"
                    )
                    if tts.is_available():
                        tts.speak(vision_reply)
                    t_spoken = time.perf_counter()
                    print(f"[Roamin] t={t_spoken - t0:.3f}s  Reply spoken (+{t_spoken - t_reply:.3f}s)")
                    print(f"[Roamin] TOTAL: {t_spoken - t0:.3f}s")
                    return  # vision fully handled — skip text-model path
                except Exception as e:
                    print(f"[Warning] Vision fast-path failed ({e}) — falling back to text description")
                    # Fall through: use text description from direct_result["result"] as tool_context

            # Non-vision direct dispatch (or vision fallback after failure)
            tool_context = direct_result["result"][:1500]
            tool_context = tool_context.encode("ascii", errors="ignore").decode("ascii")
        elif direct_result is not None:
            # Tool matched but execution failed — fall through to AgentLoop as fallback
            print(
                f"[Roamin] t={t_dispatch - t0:.3f}s  Direct dispatch FAILED "
                f"({direct_result.get('error', 'unknown')}) — falling to AgentLoop",
                flush=True,
            )
            direct_result = None  # treat as no match so AgentLoop branch runs

        if direct_result is None:
            # Layer 2: AgentLoop — full planner for complex queries
            result = {}
            goal_lower = transcription.lower()
            include_screen = any(w in goal_lower for w in ["screen", "look at", "looking at", "what am i", "what's on"])
            try:
                result = agent_loop.run(transcription, include_screen=include_screen)
            except Exception as e:
                print(f"[Warning] AgentLoop error: {e}")
                if tts.is_available():
                    tts.speak("I encountered an error processing that command.")
                return
            t_agent = time.perf_counter()
            print(
                f"[Roamin] t={t_agent - t0:.3f}s  AgentLoop done "
                f"(+{t_agent - t_stt:.3f}s) status={result.get('status')}"
            )

            status = result.get("status", "unknown")
            if status == "failed":
                if tts.is_available():
                    tts.speak("I couldn't complete that task.")
                return
            if status == "cancelled":
                if tts.is_available():
                    tts.speak("Got it, stopping.")
                return
            if status == "blocked":
                if tts.is_available():
                    tts.speak("That action needs your approval.")
                return

            # Collect tool outputs from executed steps (skip null-tool reasoning steps)
            tool_outputs = []
            for s in result.get("steps", []):
                if s.get("status") == "executed" and s.get("tool") and s.get("outcome"):
                    tool_outputs.append(f"[{s['tool']}]: {s['outcome']}")
            tool_context = "\n".join(tool_outputs)[:1500]

        # Generate reply with tool results and memory context injected
        reply = "Got it." if fact_stored else "Done."
        try:
            router = ModelRouter()
            if tool_context:
                system_content = (
                    "You are Roamin, a voice assistant. "
                    "Tool results are provided below — use them to answer the user directly. "
                    "Reply in ONE short spoken sentence. No lists, no narration."
                    f"\n\nTool results:\n{tool_context}"
                )
            else:
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
            no_think, think_max_tokens = _classify_think_level(transcription)
            if tool_context and think_max_tokens < 200:
                think_max_tokens = 200
            print(f"[Roamin] Think level: no_think={no_think}, max_tokens={think_max_tokens}")
            reply = router.respond(
                "default",
                transcription,
                messages=messages,
                max_tokens=think_max_tokens,
                temperature=0.6 if not no_think else 0.7,
                no_think=no_think,
            )
            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
            reply = re.sub(r"[^\x00-\x7F]+", "", reply).strip()
            reply = reply[:200] if reply else ("Got it." if fact_stored else "Done.")
        except Exception:
            reply = "Got it." if fact_stored else "Done."
        t_reply = time.perf_counter()
        print(f"[Roamin] t={t_reply - t0:.3f}s  Reply generated (+{t_reply - t_stt:.3f}s) → '{reply}'")

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
