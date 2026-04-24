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
from enum import Enum, auto
from pathlib import Path

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
from agent.core.voice.session import get_session
from agent.core.voice.stt import SpeechToText
from agent.core.voice.tts import TextToSpeech

try:
    from agent.core.llama_backend import unload_current_model as _unload_llm
except ImportError:

    def _unload_llm() -> None:  # type: ignore[misc]
        pass


# Patterns for wake-word prefixes that Whisper may transcribe.
# Ordered longest-first so "hey roamin" is tried before bare "roamin".
_WAKE_PREFIXES = re.compile(
    r"^(?:"
    r"hey roamin[,.\s]*"
    r"|hey roman[,.\s]*"
    r"|a roamin[,.\s]*"
    r"|a roman[,.\s]*"
    r"|roamin[,.\s]*"
    r"|roman[,.\s]*"
    r")",
    re.IGNORECASE,
)

# Patterns Whisper may produce when transcribing "hey roamin" — used to
# validate that the OWW trigger audio actually contains the wake phrase.
_WAKE_CONFIRM_RE = re.compile(
    r"hey[\s,]*ro+a?m(?:in|ing|aine?|an|ine|ba)"  # hey roamin/roaming/romaine/roman/roba
    r"|hey[\s,]*row?m"  # hey rom / hey rowm
    r"|a[\s,]+ro+a?m(?:in|ing)"  # a roamin (Whisper mishear of "hey")
    r"|ro+a?m(?:in|ing|an)\b",  # roamin/roaming/roman alone
    re.IGNORECASE,
)


def _strip_wake_prefix(text: str) -> str:
    """Remove a leading wake-word prefix from the STT transcription.

    Whisper sometimes captures the trigger phrase that OpenWakeWord already
    consumed (e.g. "Hey Roamin, search drones") or mishears it as
    "A Roman" / "Hey Roman".  Strip it so the rest of the pipeline sees
    only the user's actual command.
    """
    cleaned = _WAKE_PREFIXES.sub("", text).strip()
    # If stripping left nothing (user just said "Hey Roamin" with no command),
    # return the original so the empty-check downstream handles it.
    return cleaned if cleaned else text


def _make_request_fingerprint(transcription: str) -> str:
    """Return a SHA-256 hex digest of the normalised transcription.

    Whitespace is collapsed so minor STT variation ('search  dogs' vs 'search dogs')
    maps to the same fingerprint.
    """
    import hashlib

    normalised = " ".join(transcription.lower().split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _classify_intent(transcription: str) -> str:
    """Classify transcription as 'tool' or 'chat' using a two-token LLM call.

    Uses the loaded GGUF backend directly (bypasses ModelRouter overhead).
    Forces output to exactly two tokens at temperature=0.0 — deterministic.

    Returns 'tool' if AgentLoop should run, 'chat' if direct response is better.
    Falls back to 'tool' (conservative) on any error — running AgentLoop
    unnecessarily costs latency; skipping it when needed gives a wrong answer.
    Wrong is worse than slow.
    """
    try:
        from agent.core.llama_backend import _REGISTRY, CAPABILITY_MAP

        cap = "chat" if "chat" in CAPABILITY_MAP else "default"
        backend = _REGISTRY.get_backend(cap)
        if not backend.is_loaded():
            return "tool"  # pre-warm hasn't fired yet — conservative fallback

        prompt = (
            "You are a routing classifier. Read the user query and reply with exactly "
            "one word — either TOOL or CHAT.\n\n"
            "Reply TOOL if the query asks you to DO something on the computer: "
            "search the web, open or read a file, run a program, control an app, "
            "take a screenshot, send a message, download something, or perform "
            "any action that requires a tool.\n\n"
            "Reply CHAT if the query is a question, opinion, explanation, "
            "conversation, or anything that can be answered from knowledge alone.\n\n"
            f'User query: "{transcription}"\n'
            "Your one-word answer (TOOL or CHAT):"
        )
        result = backend.generate(prompt, max_tokens=2, temperature=0.0)
        verdict = result.strip().upper()
        if "TOOL" in verdict:
            print(f"[Roamin] Intent: TOOL — '{transcription[:60]}'", flush=True)
            return "tool"
        print(f"[Roamin] Intent: CHAT — '{transcription[:60]}'", flush=True)
        return "chat"
    except Exception as e:
        print(f"[Roamin] Intent classifier error ({e}) — defaulting to TOOL", flush=True)
        return "tool"


def _classify_think_level(text: str) -> tuple[bool, int]:
    """Classify how much thinking Roamin should do for this prompt.

    Returns:
        (no_think: bool, max_tokens: int)
        OFF  (no_think=True,  max_tokens=80)   — default, simple queries
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
        # NOTE: "think about" removed — it's a substring of "what do you think about X"
        # which is a casual opinion question, not an explicit reasoning request.
        # Use "think through X" to explicitly request think-tier reasoning.
        "think through",
        "analyze",
        "analyse",
        "explain why",
        "explain how",
        "reason through",
        "figure out",
        # NOTE: "what do you think" intentionally removed — it's a casual opinion/social phrase
        # ("what do you think about this comedian?") that does not require reasoning-tier inference.
        # It would route casual queries to think mode and exhaust the token budget on hallucination.
        # If you need reasoning about something, use "think about X" or "think through X".
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
        # 512 tokens was insufficient — the thinking phase alone consumes 300-400+ tokens,
        # leaving no budget for the actual answer. 1500 gives room for think + response.
        return False, 1500

    return True, 80  # ~60 words headroom; 120-char post-cap trims the spoken reply cleanly


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
                    f"[Roamin] Fuzzy model match: '{candidate}' -> '{matched_token}' " f"(cutoff={_FUZZY_MODEL_CUTOFF})"
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
        "what's in the mem palace",
        "what is in the mem palace",
        "what's in the mempalace",
        "what is in the mempalace",
        "what's inside the palace",
        "what is inside the palace",
        "show me the palace",
        "show me the mem palace",
        "show palace",
        "palace contents",
        "what's stored in the palace",
        "what is stored in the palace",
        "summarize the palace",
        "summarize the mem palace",
        "summarize the mempalace",
        "summarize palace",
        "summarize mem palace",
        "last entries in the palace",
        "last entries in the mem palace",
        "recent entries in the palace",
        "recent entries in the mem palace",
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


class _WakeState(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()


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
        self._state = _WakeState.IDLE
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()  # guards _state; separate from _wake_lock
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

    def _transition_to(self, state: _WakeState) -> None:
        """Move to a new state. Must be called with _state_lock held.

        Clears _stop_event unconditionally on every transition.
        Calls tts.reset_stop() when transitioning to IDLE, ensuring every
        new wake cycle and every explicit early-return starts with a clean
        _stop_flag. This means 'yes?' always plays, and progress phrases
        during PROCESSING observe any active stop signal without it being
        pre-emptively wiped.
        """
        self._state = state
        self._stop_event.clear()
        if state == _WakeState.IDLE and self._tts is not None:
            self._tts.reset_stop()
        print(f"[Roamin] State → {state.name}", flush=True)

    def _on_stop_word(self) -> None:
        """Stop callback — fires when WakeWordListener detects 'stop roamin'.

        Called from the audio thread. Thread-safe via _state_lock.

        Does NOT call _transition_to() — that would clear _stop_event and
        _stop_flag immediately, racing with the threads being signalled.
        _state is set directly; _stop_event and _stop_flag stay set until
        the next _transition_to(IDLE) clears them (at an explicit return in
        _on_wake, or at the start of the next cycle).
        """
        with self._state_lock:
            if self._state not in (_WakeState.SPEAKING, _WakeState.PROCESSING):
                return  # only interrupt during active output phases; ignore during IDLE/LISTENING
            print("[Roamin] Stop word detected — cancelling", flush=True)
            self._stop_event.set()
            self._state = _WakeState.IDLE

        try:
            if self._tts is not None:
                self._tts.stop()
        except Exception:
            pass

        try:
            if self._agent_loop is not None:
                self._agent_loop.cancel()
        except Exception:
            pass

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
        """Delegate to ``chat_engine.extract_and_store_fact``."""
        from agent.core.chat_engine import extract_and_store_fact

        return extract_and_store_fact(transcription, memory)

    def _build_memory_context(self, transcription: str, memory: MemoryManager) -> str:
        """Delegate to ``chat_engine.build_memory_context``."""
        from agent.core.chat_engine import build_memory_context

        return build_memory_context(transcription, memory)

    @staticmethod
    def _play_wake_chime() -> None:
        """Play an 880Hz chime to confirm the wake phrase was validated.

        Fires after Whisper confirms the trigger audio contains "hey roamin" —
        not on raw OWW detection. The chime signals to the user: "I heard the
        correct phrase, wait for my reply." Uses winsound.Beep (Windows system
        call, no Chatterbox dependency, no mic interference).
        """
        try:
            import winsound

            threading.Thread(
                target=lambda: winsound.Beep(880, 120),
                daemon=True,
            ).start()
        except Exception:
            pass  # non-fatal — chime is convenience, not critical path

    @staticmethod
    def _find_latest_trigger_audio() -> Path | None:
        """Return the most recently saved OWW trigger audio, if within 5s."""
        trigger_dir = Path(__file__).parents[3] / "logs" / "wake_triggers"
        if not trigger_dir.exists():
            return None
        files = sorted(trigger_dir.glob("*.wav"), key=lambda f: f.stat().st_mtime)
        if not files:
            return None
        latest = files[-1]
        if time.time() - latest.stat().st_mtime < 5.0:
            return latest
        return None

    @staticmethod
    def _validate_wake_phrase(trigger_path: Path, stt: "SpeechToText") -> bool:
        """Transcribe trigger audio and confirm it contains the wake phrase.

        Prevents OWW false positives (e.g. "hey" alone firing at 0.99) by
        running Whisper on the end of the 2s rolling buffer saved at detection
        time.

        Why last-1s only: the rolling buffer captures 2s ending at detection.
        "Hey Roamin" (~700ms) sits at the tail; the leading ~1.3s is ambient
        silence. Passing the full 2s causes Whisper to hallucinate text on the
        silence ("Takes.", "Okay.", "That's weird."). Slicing to the last 1s
        puts the actual phrase at the center of the input and eliminates the
        leading-silence hallucination problem.

        Fails OPEN on exception or missing model — so a Whisper error never
        silently blocks a legitimate wake. Fails CLOSED on empty/non-wake text.
        """
        try:
            if stt._model is None:
                return True  # Whisper not loaded — fail open

            import wave

            import numpy as np

            # Read trigger WAV — always 16kHz mono int16 (written by wake_word.py)
            with wave.open(str(trigger_path), "rb") as wf:
                sample_rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())

            audio_int16 = np.frombuffer(frames, dtype=np.int16)
            # Slice to last 1.5 seconds — OWW fires mid-phrase so the tail of
            # the 2s buffer is most likely to contain "hey roamin". 1.5s gives
            # ~800ms of leading context plus ~700ms of the wake phrase.
            audio_int16 = audio_int16[-int(sample_rate * 1.5) :]
            audio_float = audio_int16.astype(np.float32) / 32768.0

            result = stt._model.transcribe(
                audio_float,
                language="en",
                no_speech_threshold=0.6,
                initial_prompt="Hey Roamin.",  # bias decoder toward the wake phrase
            )
            text = result.get("text", "").strip()

            if not text:
                # Empty transcription = OWW fired before the phrase was complete
                # and Whisper heard only partial/quiet audio. "hey" alone reliably
                # transcribes as "Hey." — empty means the phrase was cut off, not
                # that a short sound triggered it. Fail open.
                print("[Roamin] Wake validation (PASS): <no speech — early fire, allowing>", flush=True)
                return True

            matched = bool(_WAKE_CONFIRM_RE.search(text))
            status = "PASS" if matched else "REJECT"
            print(f"[Roamin] Wake validation ({status}): '{text}'", flush=True)
            return matched
        except Exception as e:
            print(f"[Roamin] Wake validation error ({e}) — allowing through", flush=True)
            return True  # fail open on unexpected errors

    def _on_wake(self) -> None:
        """Handle wake word trigger: listen for command and execute."""
        t0 = time.perf_counter()
        print("[Roamin] Wake triggered at t=0.000", flush=True)

        # Reset state, _stop_event, and _stop_flag at the start of every cycle.
        # _on_wake() runs under _wake_lock so the previous cycle has fully exited.
        # _transition_to(IDLE) calls tts.reset_stop() — ensures "yes?" always plays
        # even if a previous cycle ended mid-PROCESSING without reaching SPEAKING.
        with self._state_lock:
            self._transition_to(_WakeState.IDLE)

        # Use pre-loaded instances or lazy-load if not provided
        tts = self._tts or TextToSpeech()
        stt = self._stt or SpeechToText()
        agent_loop = self._agent_loop or AgentLoop()

        # Phrase validation — confirm OWW trigger audio contains "hey roamin".
        # OWW currently false-fires on "hey" alone (model limitation). Whisper
        # transcribes the 2s rolling buffer saved at detection time and checks
        # it against _WAKE_CONFIRM_RE. Suppresses ~200ms of latency worth of
        # false positives; fails open on errors so legit wakes are never lost.
        trigger_path = self._find_latest_trigger_audio()
        if trigger_path is not None:
            if not self._validate_wake_phrase(trigger_path, stt):
                print("[Roamin] Wake suppressed — phrase not confirmed in trigger audio", flush=True)
                return

        # CHIME — fires here, after phrase is confirmed, BEFORE "yes?".
        # Signals to user: "I heard 'hey roamin' correctly, reply is coming."
        # Semantically distinct from "yes?" — chime = wake confirmed,
        # "yes?" = ready for your command.
        self._play_wake_chime()

        # 300ms gap between chime and "yes?" so the two sounds are clearly
        # separate — chime as confirmation, then Roamin's verbal response.
        time.sleep(0.3)

        # Greet user
        if tts.is_available():
            tts.speak("yes?")
        t_greeted = time.perf_counter()
        print(f"[Roamin] t={t_greeted - t0:.3f}s  'Yes?' spoken", flush=True)

        # GGUF pre-warm — start loading the default model during the STT recording window.
        # The user is about to speak for ~5s; we use that dead time to get the model into VRAM.
        # ModelRegistry._lock (RLock) is thread-safe: if the model is already cached this is a
        # no-op; if it's mid-load when router.respond() arrives, that call blocks briefly for
        # the remainder — still faster than the full sequential load. Fire-and-forget; errors
        # are non-fatal (model loads on demand as before).
        def _prewarm_default() -> None:
            try:
                from agent.core.llama_backend import _REGISTRY, CAPABILITY_MAP

                cap = "chat" if "chat" in CAPABILITY_MAP else "default"
                _t_pw = time.perf_counter()
                _REGISTRY.get_backend(cap)
                print(f"[Roamin] Pre-warm '{cap}' ready in {time.perf_counter() - _t_pw:.1f}s", flush=True)
            except Exception as _pw_err:
                print(f"[Roamin] Pre-warm failed ({_pw_err}) — will load on demand", flush=True)

        _prewarm_thread = threading.Thread(target=_prewarm_default, daemon=True, name="gguf-prewarm")
        _prewarm_thread.start()

        # STT — record and transcribe
        with self._state_lock:
            self._transition_to(_WakeState.LISTENING)

        transcription = None
        try:
            transcription = stt.record_and_transcribe(duration_seconds=5, stop_event=self._stop_event)
        except Exception as e:
            print(f"[Warning] STT error: {e}", flush=True)
        t_stt = time.perf_counter()
        print(f"[Roamin] t={t_stt - t0:.3f}s  STT done (+{t_stt - t_greeted:.3f}s) -> '{transcription}'", flush=True)

        if transcription is None or transcription.strip() == "":
            if tts.is_available() and not self._stop_event.is_set():
                tts.speak("Sorry, I didn't catch that.")
            with self._state_lock:
                self._transition_to(_WakeState.IDLE)
            return

        # Strip wake word prefix — Whisper sometimes transcribes the wake
        # word trigger ("Hey Roamin", "Roamin,") or mishears it as
        # "A Roman", "Hey Roman", etc.  Remove it so downstream processing
        # sees only the user's actual command.
        transcription = _strip_wake_prefix(transcription)

        # Deduplication: suppress identical transcriptions within TTL window
        _fp = _make_request_fingerprint(transcription)
        _now_fp = time.perf_counter()
        with self._pending_fingerprint_lock:
            if self._pending_fingerprint == _fp and (_now_fp - self._last_fingerprint_time) < self._fingerprint_ttl:
                print(f"[Roamin] Duplicate request suppressed (fp={_fp[:8]})", flush=True)
                if tts.is_available() and not self._stop_event.is_set():
                    tts.speak_streaming("Already on it.")
                with self._state_lock:
                    self._transition_to(_WakeState.IDLE)
                return
            self._pending_fingerprint = _fp
            self._last_fingerprint_time = _now_fp

        # Session continuity — track exchanges + handle "new conversation" command
        session = get_session()
        _lower = transcription.strip().lower()
        if _lower in ("new conversation", "start over", "reset conversation", "fresh start"):
            session.reset(reason="voice_command")
            if tts.is_available() and not self._stop_event.is_set():
                tts.speak("Starting fresh. What's up?")
            with self._state_lock:
                self._transition_to(_WakeState.IDLE)
            return

        # Add user message to session transcript
        session.add("user", transcription)

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
                        f"(+{t_reply - t_dispatch:.3f}s) -> '{vision_reply}'"
                    )
                    if tts.is_available():
                        with self._state_lock:
                            if self._stop_event.is_set():
                                self._transition_to(_WakeState.IDLE)
                                return
                            self._transition_to(_WakeState.SPEAKING)
                        tts.speak(vision_reply)
                        with self._state_lock:
                            self._transition_to(_WakeState.IDLE)
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
            else:
                # Conversational fast-path: use a two-token LLM call to decide whether
                # AgentLoop is needed. The GGUF is already pre-warmed (ENHANCE #1) so
                # this is a ~50ms cache hit — no model load overhead on the critical path.
                if _classify_intent(transcription) == "chat":
                    direct_result = {}  # sentinel: bypasses AgentLoop, goes straight to response

        # Transition to PROCESSING before AgentLoop (or response generation if bypassed).
        # Primary guard: if stop fired during LISTENING or the intent/dispatch blocks,
        # bail here before any PROCESSING work starts.
        with self._state_lock:
            if self._stop_event.is_set():
                self._transition_to(_WakeState.IDLE)
                return
            self._transition_to(_WakeState.PROCESSING)

        if direct_result is None:
            # Layer 2: AgentLoop — full planner for complex queries
            result = {}
            goal_lower = transcription.lower()
            include_screen = any(w in goal_lower for w in ["screen", "look at", "looking at", "what am i", "what's on"])

            def _progress_handler(event: dict) -> None:
                """Speak TTS cues for AgentLoop progress events."""
                phase = event.get("phase")
                if phase == "planning":
                    if tts.is_available() and not self._stop_event.is_set():
                        tts.speak("Let me think...")
                elif phase == "step_start":
                    total = event.get("total_steps", 0)
                    step_num = event.get("step", 0)
                    if total > 2 and tts.is_available() and not self._stop_event.is_set():
                        tts.speak(f"Step {step_num} of {total}.")
                elif phase == "step_done" and event.get("status") == "blocked":
                    step_num = event.get("step", 0)
                    if tts.is_available() and not self._stop_event.is_set():
                        tts.speak(f"Step {step_num} couldn't be completed, it needs approval.")

            try:
                self._agent_running_event.set()
                try:
                    result = agent_loop.run(
                        transcription,
                        include_screen=include_screen,
                        on_progress=_progress_handler,
                        session_context=session.get_context_block(),
                    )
                finally:
                    self._agent_running_event.clear()
            except Exception as e:
                print(f"[Warning] AgentLoop error: {e}")
                if tts.is_available() and not self._stop_event.is_set():
                    tts.speak("I encountered an error processing that command.")
                with self._state_lock:
                    self._transition_to(_WakeState.IDLE)
                return
            t_agent = time.perf_counter()
            print(
                f"[Roamin] t={t_agent - t0:.3f}s  AgentLoop done "
                f"(+{t_agent - t_stt:.3f}s) status={result.get('status')}"
            )

            status = result.get("status", "unknown")
            if status == "cancelled":
                if tts.is_available() and not self._stop_event.is_set():
                    tts.speak("Got it, stopping.")
                with self._state_lock:
                    self._transition_to(_WakeState.IDLE)
                return
            if status == "blocked":
                if tts.is_available() and not self._stop_event.is_set():
                    tts.speak("That requires your approval. Check your notifications.")
                _handle_blocked_steps(result.get("blocked_steps", []), memory)
                with self._state_lock:
                    self._transition_to(_WakeState.IDLE)
                return
            # status == "failed": do NOT return — fall through to ModelRouter so
            # conversational queries ("what is X?", "who are you?") still get answered.

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

        # MemPalace fallback — if direct dispatch didn't catch it and AgentLoop
        # didn't produce useful tool output, try MemPalace directly.
        _mp_triggers = ["palace", "mempalace", "mem palace", "memory search", "search my mem"]
        if any(t in transcription.lower() for t in _mp_triggers) and not tool_context:
            try:
                _lower_mp = transcription.lower()
                # Overview queries ("what's in the palace", "summarize entries")
                # → use mempalace_status which returns all stored entries
                _overview_words = ["what", "summarize", "summary", "entries", "show", "list", "contents", "status"]
                if any(w in _lower_mp for w in _overview_words):
                    _mp_result = registry.execute("mempalace_status", {})
                else:
                    # Specific search query — strip noise words for cleaner matching
                    _clean_query = re.sub(
                        r"\b(?:palace|mempalace|mem palace|search|find|look up|tell me about|what is|what are)\b",
                        "",
                        _lower_mp,
                    ).strip()
                    _mp_result = registry.execute("mempalace_search", {"query": _clean_query or transcription})

                _mp_ok = _mp_result and (_mp_result.get("ok") or _mp_result.get("success"))
                if _mp_ok and _mp_result.get("result"):
                    tool_context = f"[mempalace]: {str(_mp_result['result'])[:1500]}"
                    print(f"[Roamin] MemPalace context injected for voice query: {transcription[:60]}")
            except Exception as _mp_err:
                print(f"[Warning] MemPalace voice search failed: {_mp_err}")

        # Generate reply with tool results and memory context injected
        reply = "Got it." if fact_stored else "Done."
        try:
            router = ModelRouter()

            # Detect per-request model override (e.g. "use ministral to explain X")
            model_override, clean_text, override_name = _detect_model_override(transcription)
            task_type = model_override or "default"
            if model_override:
                print(f"[Roamin] Model override: {override_name} (capability: {model_override})")

            # Conversational fast-path: use local GGUF 'chat' model instead of LM Studio.
            # 'default' routes to LM Studio via HTTP (~10-24s). 'chat' uses the same
            # DeepSeek R1 8B model loaded in-process — no HTTP overhead, same quality.
            # Only applies when AgentLoop was bypassed (no tool output) and no explicit override.
            if not model_override and not tool_context:
                no_think_check, _ = _classify_think_level(transcription)
                if no_think_check:
                    task_type = "chat"
                    print("[Roamin] Fast-path: using local 'chat' model (no LM Studio)", flush=True)

            # Two-layer system prompt: task instructions + Roamin sidecar context
            from agent.core.chat_engine import build_sidecar_context

            # Use cleaned transcription (trigger phrase stripped) in prompt
            prompt_text = clean_text if model_override else transcription
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
            stream_think = not no_think
            if stream_think and task_type not in ("reasoning", "code"):
                task_type = "reasoning"

            # Layer 1: Task instructions (short, lets model use its training)
            if not no_think and not tool_context:
                # Think-tier: 2 sentences max, start directly with the answer.
                # "Okay, let's think through..." preambles waste ~47 chars of the voice budget
                # before the real answer starts. No preamble = more answer in fewer chars.
                layer1 = (
                    "Answer in exactly 2 spoken sentences. "
                    "Start the first word with your answer — no 'Okay', no preamble, no transition. "
                    "Be accurate and direct. No markdown, no lists."
                )
            elif tool_context:
                layer1 = (
                    "Tool results are provided below. Use them to answer the user directly. "
                    "Reply in ONE short spoken sentence. Plain text only.\n\n"
                    f"Tool results:\n{tool_context}"
                )
            else:
                layer1 = (
                    "Reply in one direct spoken sentence, 12 words maximum. "
                    "Be concise. Plain text only. No hedging, no lists, no narration."
                )

            # Layer 2: Roamin sidecar (persona + context)
            # NOTE: MemPalace data is already in tool_context (layer1) when present.
            # Don't double-inject it into the sidecar — wastes tokens and confuses model.
            #
            # Conversational fast-path: skip full sidecar (1500-char persona + session dump).
            # The full sidecar causes the model to hallucinate personal details from session
            # context and respond in a verbose narrative register instead of voice-appropriate
            # one-sentence answers. For no-think / no-tool queries, only the anti-hallucination
            # rules are needed. Full sidecar is reserved for tool-using and think-tier queries.
            if not tool_context:
                # No tool context: use rule-only sidecar for both conversational and think-tier.
                # Full sidecar (1500-char persona) causes token budget waste on context analysis.
                # Identity statement ("You are Roamin, a voice assistant") causes the model to
                # respond with self-description when it doesn't know the answer — "I am Roamin,
                # a voice assistant designed to..." — instead of "I don't know." Rules only,
                # no identity claim: the model's training already handles question-answering.
                layer2 = (
                    "Answer the question directly and concisely. "
                    "If you don't know something, say so briefly. "
                    "Never invent information. Plain text only, no markdown."
                )
            else:
                # Tool context present: inject full sidecar so the model understands who it
                # serves when synthesizing tool results into a response.
                layer2 = build_sidecar_context(
                    memory_context=memory_context,
                    mempalace_context="",
                    session_context="",
                )

            system_content = f"{layer1}\n\n{layer2}"
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
                temperature=0.3 if not no_think else 0.2,  # low temp = less hallucination
                no_think=no_think,
                stream_think=stream_think,
            )
            # Strip reasoning blocks and markdown — same pipeline as chat_engine.py
            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
            reply = re.sub(r"</?[\w]+>", "", reply).strip()
            # NOTE: leakage safety net removed. The unclosed-think-block case is now handled
            # in llama_backend._stream_with_think_print by appending </think> before return,
            # which ensures the regex always has a matching pair to strip. Pattern-matching on
            # the reply start caused false positives when valid answers began with "Okay, so..."
            reply = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", reply)
            reply = re.sub(r"_{1,2}(.+?)_{1,2}", r"\1", reply)
            reply = re.sub(r"^#{1,6}\s+", "", reply, flags=re.MULTILINE)
            reply = re.sub(r"^\s*[-*]\s+", "", reply, flags=re.MULTILINE)
            reply = re.sub(r"\n{3,}", "\n\n", reply).strip()
            reply = re.sub(r"[^\x00-\x7F]+", "", reply).strip()
            # Length cap — both paths: voice output must stay within TTS budget.
            # Conversational (no_think): 120 chars (~20 words) → ~10s TTS
            # Think-tier: 150 chars (~25 words, 2 sentences) → ~15-18s TTS
            # Truncate at last word boundary to avoid cutting mid-word.
            _cap = 120 if no_think else 150
            if len(reply) > _cap:
                reply = reply[:_cap].rsplit(" ", 1)[0]
            reply = reply if reply else ("Got it." if fact_stored else "Done.")
        except Exception:
            reply = "Got it." if fact_stored else "Done."
        t_reply = time.perf_counter()
        print(f"[Roamin] t={t_reply - t0:.3f}s  Reply generated (+{t_reply - t_stt:.3f}s) -> '{reply}'")

        # NOTE: _unload_llm() intentionally removed here.
        # Previously called before every TTS synthesis to free VRAM for Chatterbox.
        # Cost: 4.7s model reload on every subsequent inference call (confirmed in logs).
        # The assumption that GGUF + Chatterbox cannot coexist in VRAM is unverified.
        # If Chatterbox synthesis fails with an OOM error, restore this call conditionally
        # (e.g., only on explicit memory pressure, not unconditionally every interaction).

        # TTS — route based on reply complexity.
        # Conversational fast-path (no_think): use speak() — single Chatterbox synthesis call.
        # speak_streaming() splits on sentence boundaries; each split = one HTTP round-trip to
        # Chatterbox (~3-4s minimum overhead per call). "One. Two. Three. Four." → 4 calls → 15s.
        # Single speak() call = 1 synthesis request regardless of sentence count → ~5-7s.
        # Think-tier / tool-context replies may span multiple long sentences where streaming
        # pipeline (synthesize N+1 while playing N) meaningfully reduces perceived latency.
        # TTS routing:
        # Conversational (no_think, 120-char cap, 1 sentence): speak() — single synthesis call.
        #   At 120 chars, no streaming benefit; single call avoids HTTP overhead per sentence.
        # Think-tier (150-char cap, 2 sentences): speak_streaming() — pipeline synthesis.
        #   With 2 sentences, sentence 2 synthesizes while sentence 1 plays.
        #   User hears first sentence after ~8s instead of waiting for all ~15s of synthesis.
        with self._state_lock:
            if self._stop_event.is_set():
                self._transition_to(_WakeState.IDLE)
                return
            self._transition_to(_WakeState.SPEAKING)

        if tts.is_available():
            if no_think:
                tts.speak(reply)
            else:
                tts.speak_streaming(reply)
        t_spoken = time.perf_counter()
        print(f"[Roamin] t={t_spoken - t0:.3f}s  Reply spoken (+{t_spoken - t_reply:.3f}s)")
        print(f"[Roamin] TOTAL: {t_spoken - t0:.3f}s")

        with self._state_lock:
            self._transition_to(_WakeState.IDLE)

        # Show approval toasts for any blocked steps (non-fatal)
        _handle_blocked_steps(result.get("blocked_steps", []) if result else [], memory)

        # Store assistant reply in session transcript
        try:
            session.add("assistant", reply)
        except Exception:
            pass

        # Store conversation in memory (uses session ID instead of hardcoded value)
        try:
            model_label = override_name or task_type
            memory.write_to_memory(
                "conversation",
                {"session_id": session.session_id, "model_used": model_label, "content": f"User: {transcription}"},
            )
        except Exception:
            pass
