"""Wake listener with hotkey trigger."""

from __future__ import annotations

import base64
import difflib
import io
import json
import re
import sys
import threading
import time
import traceback

try:
    import keyboard
except ImportError:
    keyboard = None

from agent.core import paths, ports
from agent.core.agent_loop import AgentLoop
from agent.core.memory import MemoryManager
from agent.core.model_router import ModelRouter
from agent.core.screen_observer import _notify_approval_toast
from agent.core.tool_registry import ToolRegistry
from agent.core.voice.stt import SpeechToText
from agent.core.voice.tts import TextToSpeech

try:
    from agent.core.llama_backend import unload_current_model as _unload_llm
except ImportError:

    def _unload_llm() -> None:  # type: ignore[misc]
        pass


def _make_request_fingerprint(transcription: str) -> str:
    """Return a SHA-256 hex digest of the normalised transcription.

    Whitespace is collapsed so minor STT variation ('search  dogs' vs 'search dogs')
    maps to the same fingerprint.
    """
    import hashlib

    normalised = " ".join(transcription.lower().split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


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


# ---------------------------------------------------------------------------
# Voice model override — per-request routing to non-default models
# ---------------------------------------------------------------------------

# Stage 1: Exact prefix triggers — phrases without a spoken model name,
# plus multi-word model references that Whisper reliably produces.
_EXACT_MODEL_TRIGGERS: list[tuple[str, str, str]] = [
    # Reasoning triggers → DeepSeek R1 8B
    ("think really hard about ", "reasoning", "DeepSeek R1 8B"),
    ("think hard about ", "reasoning", "DeepSeek R1 8B"),
    ("really think about ", "reasoning", "DeepSeek R1 8B"),
    ("reason through ", "reasoning", "DeepSeek R1 8B"),
    ("deeply analyze ", "reasoning", "DeepSeek R1 8B"),
    ("deep dive into ", "reasoning", "DeepSeek R1 8B"),
    # "deep seek" / "deep-seek" — Whisper splits or hyphenates "deepseek"
    ("use deep seek to ", "reasoning", "DeepSeek R1 8B"),
    ("use deep seek ", "reasoning", "DeepSeek R1 8B"),
    ("use deep-seek to ", "reasoning", "DeepSeek R1 8B"),
    ("use deep-seek ", "reasoning", "DeepSeek R1 8B"),
    ("ask deep seek to ", "reasoning", "DeepSeek R1 8B"),
    ("ask deep seek ", "reasoning", "DeepSeek R1 8B"),
    ("ask deep-seek to ", "reasoning", "DeepSeek R1 8B"),
    ("ask deep-seek ", "reasoning", "DeepSeek R1 8B"),
    # Coder triggers (no model name spoken) → Qwen3 Coder 80B
    ("use the coder to ", "code", "Qwen3 Coder 80B"),
    ("use the coder ", "code", "Qwen3 Coder 80B"),
    ("use coder to ", "code", "Qwen3 Coder 80B"),
    ("use coder ", "code", "Qwen3 Coder 80B"),
    ("use the big model to ", "code", "Qwen3 Coder 80B"),
    ("use the big model ", "code", "Qwen3 Coder 80B"),
]

# Stage 2: Fuzzy model name tokens.
# Maps the canonical model name token → (capability_key, friendly_name).
# Whisper garbles of these tokens are caught by difflib fuzzy matching.
_FUZZY_MODEL_TOKENS: dict[str, tuple[str, str]] = {
    "ministral": ("ministral_reasoning", "Ministral 14B"),
    "deepseek": ("reasoning", "DeepSeek R1 8B"),
}

# Verbs that precede a spoken model name ("use X", "ask X", "hey X", "with X")
_MODEL_VERB_TRIGGERS: frozenset[str] = frozenset({"use", "ask", "with", "hey"})

# Similarity threshold for fuzzy model name matching (0.0–1.0).
# 0.72 catches "ministerl"→"ministral" (≈0.78) while rejecting unrelated words.
_FUZZY_MODEL_CUTOFF = 0.72

# Minimum max_tokens per capability when a voice model override is active.
# Reasoning models emit <think> chains (300-500 tokens) before the spoken answer —
# without a higher floor the chain crowds out the reply and it gets truncated.
_CAPABILITY_MIN_TOKENS: dict[str, int] = {
    "reasoning": 2048,
    "analysis": 2048,
    "ministral_reasoning": 2048,
    "ministral": 1024,
    "ministral_vision": 1024,
    "code": 1024,
    "heavy_code": 2048,
}


def _detect_model_override(transcription: str) -> tuple[str | None, str, str | None]:
    """Detect voice model-switching triggers in the transcription.

    Two-stage detection:
      1. Exact prefix match for non-model-name phrases (e.g. "think hard about")
         and multi-word model references Whisper reliably produces ("deep seek").
      2. Fuzzy match for verb + model-name patterns — catches Whisper garbles
         like "use ministerl" → "ministral" without enumerating all variants.

    Returns:
        (capability_override, cleaned_transcription, model_name)
        - capability_override: CAPABILITY_MAP key, or None if no match
        - cleaned_transcription: transcription with trigger stripped, or original
        - model_name: human-friendly model name for logging, or None
    """
    lower = transcription.lower().strip()

    # --- Stage 1: Exact prefix match ---
    for trigger, capability, model_name in _EXACT_MODEL_TRIGGERS:
        if lower.startswith(trigger):
            cleaned = transcription[len(trigger) :].strip()
            if cleaned:
                return capability, cleaned, model_name

    # --- Stage 2: Verb + fuzzy model name ---
    words = lower.split()
    if len(words) >= 2 and words[0] in _MODEL_VERB_TRIGGERS:
        candidate = words[1]
        matches = difflib.get_close_matches(candidate, _FUZZY_MODEL_TOKENS.keys(), n=1, cutoff=_FUZZY_MODEL_CUTOFF)
        if matches:
            matched_token = matches[0]
            capability, model_name = _FUZZY_MODEL_TOKENS[matched_token]
            # Rebuild cleaned prompt: drop verb + model word + optional "to" connector
            rest = words[2:]
            if rest and rest[0] == "to":
                rest = rest[1:]
            cleaned = " ".join(rest).strip()
            if cleaned:
                print(
                    f"[Roamin] Fuzzy model match: '{candidate}' → '{matched_token}' " f"(cutoff={_FUZZY_MODEL_CUTOFF})"
                )
                return capability, cleaned, model_name

    return None, transcription, None


def _try_direct_dispatch(transcription: str, registry: ToolRegistry) -> dict | None:
    """Match transcription to a tool directly, bypassing the AgentLoop planner.

    Returns tool result dict if matched, None to fall through to AgentLoop.
    """
    lower = transcription.lower()

    # --- MemPalace (must precede web_search — "search my memories" would match the broad search regex) ---
    _MEMORY_SEARCH_TRIGGERS = [
        "search my memories for ",
        "search my memories ",
        "search memories for ",
        "my memories for ",
        "search the palace for ",
        "search the palace ",
        "search palace for ",
        "mempalace search ",
        "mem palace search ",
    ]
    for trigger in _MEMORY_SEARCH_TRIGGERS:
        if trigger in lower:
            idx = lower.index(trigger) + len(trigger)
            query = transcription[idx:].strip().rstrip(".?!")
            if query:
                print(f"[Roamin] Direct dispatch: mempalace_search('{query}')")
                return registry.execute("mempalace_search", {"query": query})

    _PALACE_STATUS_TRIGGERS = [
        "palace status",
        "mempalace status",
        "mem palace status",
        "what's in the palace",
        "what is in the palace",
        "what's inside the palace",
        "what is inside the palace",
        "show me the palace",
        "show palace",
        "palace contents",
        "what's stored in the palace",
        "what is stored in the palace",
    ]
    if any(t in lower for t in _PALACE_STATUS_TRIGGERS):
        print("[Roamin] Direct dispatch: mempalace_status()")
        return registry.execute("mempalace_status", {})

    # --- Web search ---
    for trigger in [
        "web search for ",
        "web search ",
        "do a web search for ",
        "do a web search ",
        "do a search for ",
        "do a search on ",
        "search the web for ",
        "search the web ",
        "search for ",
        "look up ",
        "google ",
        "find out about ",
        "find out ",
    ]:
        if trigger in lower:
            idx = lower.index(trigger) + len(trigger)
            query = transcription[idx:].strip().rstrip(".?!")
            if query:
                print(f"[Roamin] Direct dispatch: web_search('{query}')")
                return registry.execute("web_search", {"query": query})

    # Broader regex: catches "search drone", "search the word drone", etc.
    m = re.search(r"\bsearch\b\s+(?:for\s+|the\s+web\s+(?:for\s+)?|on\s+|the\s+word\s+)?(.+)", lower)
    if m:
        query = transcription[m.start(1) :].strip().rstrip(".?!")
        if query and len(query) > 2:
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
    screen_patterns = [
        r"what(?:'s| is| am i seeing| do you see| can you see) on (?:my |the )?screen",
        r"what(?:'s| is) on (?:my |the )?display",
        r"what am i (?:looking|staring) at",
        r"describe (?:my |the |what(?:'s| is) on (?:my |the )?)?screen",
        r"(?:look|looking) at (?:my |the )?screen",
        r"(?:see|read|tell me about) (?:my |the )?screen",
        r"what(?:'s| is) (?:this|that) on (?:my )?screen",
        r"take a (?:screen ?shot|screenshot)",
        r"screen ?shot",
        r"what(?:'s| is) (?:on )?(?:my )?(?:screen|display|monitor)",
    ]
    if any(re.search(p, lower) for p in screen_patterns):
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


def _handle_blocked_steps(blocked_steps: list[dict], memory: MemoryManager) -> None:
    """Persist blocked steps and show an approval toast for each."""
    if not blocked_steps:
        return
    # Discover Control API port from discovery file
    port = ports.CONTROL_API_DEFAULT_PORT
    try:
        discovery_file = paths.get_project_root() / ".loom" / "control_api_port.json"
        port = json.loads(discovery_file.read_text()).get("port", port)
    except Exception:
        pass
    for step in blocked_steps:
        try:
            aid = memory.store_pending_approval(
                task_run_id=None,
                step_number=step.get("step", 0),
                tool=step.get("tool"),
                action=step.get("action", ""),
                params_json=None,
                risk=step.get("risk", "high"),
            )
            _notify_approval_toast(aid, step.get("action", ""), step.get("tool"), port)
        except Exception:
            pass


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
        self._last_wake_time = 0  # Track last wake trigger time (seconds)
        self._wake_debounce_interval = 0.5  # Ignore triggers within 500ms
        self._agent_running_event = threading.Event()  # Set while AgentLoop.run() is executing
        # Request deduplication — suppress identical transcriptions within the TTL window
        self._pending_fingerprint: str | None = None
        self._pending_fingerprint_lock = threading.Lock()
        self._fingerprint_ttl = 2.0  # seconds; set to 0.0 in tests to disable
        self._last_fingerprint_time: float = 0.0

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
            keyboard.add_hotkey(self._hotkey, self._on_wake_thread, suppress=True)
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
        """Call _on_wake in a new thread (non-blocking). Drops if already running or recently triggered."""
        import time

        now = time.time()

        # Debounce: reject triggers within 500ms of last one (keyboard bounce/repeat)
        if now - self._last_wake_time < self._wake_debounce_interval:
            elapsed_ms = (now - self._last_wake_time) * 1000
            print(f"[Roamin] Wake debounced (fired {elapsed_ms:.0f}ms after last)")
            return

        self._last_wake_time = now

        if not self._wake_lock.acquire(blocking=False):
            if self._agent_running_event.is_set() and self._agent_loop is not None:
                self._agent_loop.cancel()
                _tts = self._tts
                if _tts is not None:
                    threading.Thread(
                        target=lambda: _tts.speak("Got it, stopping."),
                        daemon=True,
                    ).start()
                print("[Roamin] Cancelled active agent loop via hotkey")
            else:
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
                # Clear dedup fingerprint so same query can run again after this wake completes
                with self._pending_fingerprint_lock:
                    self._pending_fingerprint = None
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

        # Deduplication: suppress identical transcriptions within TTL window
        _fp = _make_request_fingerprint(transcription)
        _now_fp = time.perf_counter()
        with self._pending_fingerprint_lock:
            if self._pending_fingerprint == _fp and (_now_fp - self._last_fingerprint_time) < self._fingerprint_ttl:
                print(f"[Roamin] Duplicate request suppressed (fp={_fp[:8]})", flush=True)
                if tts.is_available():
                    tts.speak_streaming("Already on it.")
                return
            self._pending_fingerprint = _fp
            self._last_fingerprint_time = _now_fp

        # Memory — extract facts and build context before AgentLoop
        memory = MemoryManager()
        fact_stored = self._extract_and_store_fact(transcription, memory)
        memory_context = self._build_memory_context(transcription, memory)

        # Layer 1: Direct tool dispatch — pattern match to skip AgentLoop
        # Use agent_loop.registry (has plugins loaded) instead of a fresh ToolRegistry()
        registry = agent_loop.registry
        direct_result = _try_direct_dispatch(transcription, registry)
        t_dispatch = time.perf_counter()

        tool_context = ""
        result = None  # Initialize before conditionals; overwritten by AgentLoop if used
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

        # Think-tier queries bypass AgentLoop — tool execution adds no value for reasoning tasks
        if direct_result is None:
            _precheck_no_think, _ = _classify_think_level(transcription)
            if not _precheck_no_think:
                print("[Roamin] Think-tier query — bypassing AgentLoop, routing to reasoning LLM", flush=True)
                direct_result = {}  # sentinel: prevents AgentLoop; tool_context stays ""

        if direct_result is None:
            # Layer 2: AgentLoop — full planner for complex queries
            result = {}
            goal_lower = transcription.lower()
            include_screen = any(w in goal_lower for w in ["screen", "look at", "looking at", "what am i", "what's on"])

            def _progress_handler(event: dict) -> None:
                """Speak TTS cues for AgentLoop progress events."""
                phase = event.get("phase")
                if phase == "planning":
                    if tts.is_available():
                        tts.speak("Let me think...")
                elif phase == "step_start":
                    total = event.get("total_steps", 0)
                    step_num = event.get("step", 0)
                    if total > 2 and tts.is_available():
                        tts.speak(f"Step {step_num} of {total}.")
                elif phase == "step_done" and event.get("status") == "blocked":
                    step_num = event.get("step", 0)
                    if tts.is_available():
                        tts.speak(f"Step {step_num} couldn't be completed, it needs approval.")

            try:
                self._agent_running_event.set()
                try:
                    result = agent_loop.run(
                        transcription,
                        include_screen=include_screen,
                        on_progress=_progress_handler,
                    )
                finally:
                    self._agent_running_event.clear()
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
                    tts.speak("That requires your approval. Check your notifications.")
                _handle_blocked_steps(result.get("blocked_steps", []), memory)
                return

            # Collect tool outputs from executed steps (skip null-tool reasoning steps)
            tool_outputs = []
            for s in result.get("steps", []):
                if s.get("status") == "executed" and s.get("tool") and s.get("outcome"):
                    tool_outputs.append(f"[{s['tool']}]: {s['outcome']}")

            # Safety net: AgentLoop ran but skipped tools — force web_search if user clearly wanted one
            if not tool_outputs and any(
                w in transcription.lower() for w in ["search", "look up", "find out", "google"]
            ):
                sr = registry.execute("web_search", {"query": transcription})
                if sr.get("ok"):
                    tool_outputs.append(f"[web_search]: {sr['result'][:1500]}")
                    print(f"[Roamin] AgentLoop safety net: forced web_search for '{transcription[:60]}'")

            tool_context = "\n".join(tool_outputs)[:1500]

        # Generate reply with tool results and memory context injected
        reply = "Got it." if fact_stored else "Done."
        try:
            router = ModelRouter()

            # Detect per-request model override (e.g. "use ministral to explain X")
            model_override, clean_text, override_name = _detect_model_override(transcription)
            task_type = model_override or "default"
            if model_override:
                print(f"[Roamin] Model override: {override_name} (capability: {model_override})")

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

            # Use cleaned transcription (trigger phrase stripped) in prompt
            prompt_text = clean_text if model_override else transcription
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt_text},
            ]
            no_think, think_max_tokens = _classify_think_level(transcription)

            # Model override: apply per-capability minimum token floor.
            # Reasoning/code models need room for <think> chains + a complete answer.
            if model_override:
                capability_min = _CAPABILITY_MIN_TOKENS.get(model_override, 512)
                if no_think:
                    no_think = False
                think_max_tokens = max(think_max_tokens, capability_min)

            if tool_context and think_max_tokens < 200:
                think_max_tokens = 200
            stream_think = not no_think  # Stream thinking to terminal when think mode is active
            if stream_think and task_type not in ("reasoning", "code"):
                # Default/chat model won't generate <think> tags — route to reasoning model
                task_type = "reasoning"

            # Think-tier queries get a system prompt that allows detailed responses
            if not no_think and not tool_context:
                system_content = (
                    "You are Roamin, a voice assistant. "
                    "The user wants a thoughtful, detailed response. "
                    "Give a thorough answer in natural spoken language. "
                    "You may use multiple sentences. No markdown, no lists."
                )
                if memory_context:
                    system_content += f"\n\n{memory_context}"
                messages = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt_text},
                ]

            print(
                f"[Roamin] Think level: no_think={no_think}, max_tokens={think_max_tokens}"
                f", stream_think={stream_think}, model={task_type}"
            )
            reply = router.respond(
                task_type,
                prompt_text,
                messages=messages,
                max_tokens=think_max_tokens,
                temperature=0.6 if not no_think else 0.7,
                no_think=no_think,
                stream_think=stream_think,
            )
            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
            reply = re.sub(r"[^\x00-\x7F]+", "", reply).strip()
            reply = re.sub(r"</?[\w]*>?\s*$", "", reply).strip()  # strip trailing partial tags (</s>, </, </think>)
            # Think-tier: let model finish its full output; OFF-tier: keep voice replies short
            if no_think:
                reply = reply[:200] if reply else ("Got it." if fact_stored else "Done.")
            else:
                reply = reply if reply else ("Got it." if fact_stored else "Done.")
        except Exception:
            reply = "Got it." if fact_stored else "Done."
        t_reply = time.perf_counter()
        print(f"[Roamin] t={t_reply - t0:.3f}s  Reply generated (+{t_reply - t_stt:.3f}s) → '{reply}'")

        # Unload LLM before TTS — frees VRAM so Chatterbox can synthesize without contention
        _unload_llm()

        # TTS — speak reply (streaming pipeline for multi-sentence LLM replies)
        if tts.is_available():
            tts.speak_streaming(reply)
        t_spoken = time.perf_counter()
        print(f"[Roamin] t={t_spoken - t0:.3f}s  Reply spoken (+{t_spoken - t_reply:.3f}s)")
        print(f"[Roamin] TOTAL: {t_spoken - t0:.3f}s")

        # Show approval toasts for any blocked steps (non-fatal)
        _handle_blocked_steps(result.get("blocked_steps", []) if result else [], memory)

        # Store conversation in memory
        try:
            model_label = override_name or "Qwen3-VL-8B"
            memory.write_to_memory(
                "conversation",
                {"session_id": "voice_interface", "model_used": model_label, "content": f"User: {transcription}"},
            )
        except Exception:
            pass
