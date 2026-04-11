"""Unified message-processing pipeline for Roamin.

This module is the canonical "brain" of Roamin — it turns a user message
into a grounded, memory-aware, tool-augmented conversational reply.

Both the voice path (``wake_listener``) and the chat overlay path
(``control_api /chat``) call ``process_message()`` so that every
capability (MemoryManager, MemPalace, AgentLoop tools, session context)
is automatically available in both surfaces without separate wiring.
"""

from __future__ import annotations

import logging
import pathlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.core.memory import MemoryManager
    from agent.core.voice.session import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared AgentLoop singleton with plugins loaded
# ---------------------------------------------------------------------------
# chat_engine.process_message() is called on every chat request.  Creating a
# fresh AgentLoop() each time produces a bare registry with NO plugins — so
# mempalace_search is never registered for the chat path.  Instead we create
# ONE shared loop at import time and load plugins into it once.

_chat_loop = None
_chat_loop_lock = None


def _get_chat_loop():
    """Return (or lazily create) the module-level AgentLoop with plugins loaded."""
    global _chat_loop, _chat_loop_lock

    # Initialise the lock on first access (avoids import-time threading overhead)
    if _chat_loop_lock is None:
        import threading

        _chat_loop_lock = threading.Lock()

    if _chat_loop is not None:
        return _chat_loop

    with _chat_loop_lock:
        if _chat_loop is not None:  # double-checked locking
            return _chat_loop

        from agent.core.agent_loop import AgentLoop
        from agent.plugins import load_plugins

        loop = AgentLoop()
        try:
            load_plugins(loop.registry)
            logger.info("[chat_engine] Plugins loaded into chat AgentLoop registry")
        except Exception as exc:
            logger.warning("[chat_engine] Plugin load failed (MemPalace may be unavailable): %s", exc)

        _chat_loop = loop
        return _chat_loop


# ---------------------------------------------------------------------------
# Fact extraction
# ---------------------------------------------------------------------------

_FACT_PATTERNS = [
    r"remember (?:that )?my (.+?) is (.+)",
    r"my (.+?) is (.+)",
    r"save (?:that )?my (.+?) is (.+)",
    r"note (?:that )?my (.+?) is (.+)",
]


def extract_and_store_fact(message: str, memory: MemoryManager) -> bool:
    """Detect ``my X is Y`` patterns and persist as a named_fact.

    Returns ``True`` if a fact was successfully stored.
    """
    lower = message.lower()
    for pattern in _FACT_PATTERNS:
        m = re.search(pattern, lower)
        if m:
            fact_name = m.group(1).strip().rstrip(".")
            fact_value = m.group(2).strip().rstrip(".")
            try:
                memory.write_to_memory("named_fact", {"fact_name": fact_name, "value": fact_value})
                logger.info("Stored fact: '%s' = '%s'", fact_name, fact_value)
                return True
            except Exception as exc:
                logger.warning("Failed to store fact: %s", exc)
    return False


# ---------------------------------------------------------------------------
# Memory context
# ---------------------------------------------------------------------------


def build_memory_context(message: str, memory: MemoryManager) -> str:
    """Query ChromaDB + named facts and return a context block for injection."""
    parts: list[str] = []

    # Semantic search via MemoryManager (ChromaDB)
    try:
        results = memory.search_memory(message)
        docs = results.get("documents", [])
        if docs:
            parts.append("Relevant memories: " + " | ".join(docs[:3]))
    except Exception:
        pass

    # Named facts — inject all so the model can decide relevance in chat,
    # but also flag specifically relevant ones
    try:
        from agent.core.memory.memory_store import MemoryStore

        store = MemoryStore()
        all_facts = store.get_all_named_facts() if hasattr(store, "get_all_named_facts") else []
    except Exception:
        all_facts = []

    if all_facts:
        fact_strs = [f"{f['fact_name']}: {f['value']}" for f in all_facts]
        parts.append("Known facts about the user: " + ", ".join(fact_strs))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# MemPalace context (optional plugin)
# ---------------------------------------------------------------------------


def build_mempalace_context(message: str, registry) -> str:
    """Call the mempalace_search tool if registered; return context or ``""``."""
    try:
        result = registry.execute("mempalace_search", {"query": message})
        # Plugin returns {"success": True, ...} — check both "ok" and "success"
        ok = result and (result.get("ok") or result.get("success"))
        if ok and result.get("result"):
            text = str(result["result"])[:1000]
            return f"MemPalace results:\n{text}"
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Sidecar prompt — persona + context, NOT overriding instructions
# ---------------------------------------------------------------------------

_SIDECAR_PATH = pathlib.Path(__file__).parent / "system_prompt.txt"


def build_sidecar_context(
    *,
    memory_context: str = "",
    mempalace_context: str = "",
    session_context: str = "",
) -> str:
    """Build the Roamin persona sidecar block from system_prompt.txt + runtime context.

    This is injected AFTER the model's task-specific instructions so the model
    retains its native training (instruction-following, reasoning, etc.) while
    also knowing who it serves and what context is available.

    Returns a labeled context block string.
    """
    parts: list[str] = ["[Roamin Context]"]

    # Load persona from canonical file — skip the first line which is a
    # directive ("You are Roamin...") that would override model training.
    # Everything from "WHO YOU SERVE" onward is context, not instruction.
    try:
        raw = _SIDECAR_PATH.read_text(encoding="utf-8").strip()
        # Skip the first paragraph (the "You are Roamin..." instruction line)
        # and start from the structured context sections
        sections_start = raw.find("WHO YOU SERVE")
        if sections_start != -1:
            persona = raw[sections_start:]
        else:
            persona = raw
        # Trim to keep token budget reasonable — keep first ~1500 chars
        if len(persona) > 1500:
            persona = persona[:1500].rsplit("\n", 1)[0]
        parts.append(persona)
    except FileNotFoundError:
        parts.append(
            "You are serving Asherre, a neurodivergent developer. "
            "Be direct, warm, no condescension. Plain text only."
        )

    # Anti-hallucination rules (always present, compact)
    parts.append(
        "RULES: Never invent information. If unsure, say so. "
        "Only reference MemPalace or stored memories if they appear below. "
        "Plain text only, no markdown."
    )

    if memory_context:
        parts.append(memory_context)
    if mempalace_context:
        parts.append(f"MemPalace search results:\n{mempalace_context}")
    if session_context:
        # Truncate to avoid context snowballing
        ctx = session_context[-800:] if len(session_context) > 800 else session_context
        parts.append(f"Recent conversation:\n{ctx}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Direct tool dispatch — skip AgentLoop for single-tool requests
# ---------------------------------------------------------------------------

_WEB_SEARCH_TRIGGERS = [
    "search for ",
    "search ",
    "look up ",
    "google ",
    "find out about ",
    "what's the weather",
    "what is the weather",
    "weather in ",
]

_CONVERSATIONAL_PATTERNS = [
    "who are you",
    "what are you",
    "how are you",
    "what can you do",
    "hello",
    "hi ",
    "hey ",
    "thanks",
    "thank you",
    "good morning",
    "good night",
    "what's up",
    "whats up",
]


def _try_direct_dispatch(message: str, registry) -> str:
    """Attempt to handle a message with a single tool call, bypassing AgentLoop.

    Returns tool_context string if dispatched, or "" if no match.
    """
    lower = message.lower()

    # Web search
    for trigger in _WEB_SEARCH_TRIGGERS:
        if trigger in lower:
            try:
                result = registry.execute("web_search", {"query": message})
                if result and (result.get("ok") or result.get("success")) and result.get("result"):
                    return f"[web_search]: {str(result['result'])[:1500]}"
            except Exception:
                pass
            break  # Only try once

    return ""


def _is_conversational(message: str) -> bool:
    """Return True if the message is casual conversation that needs no tools."""
    lower = message.lower().strip()
    # Short greetings / pleasantries
    if len(lower) < 40 and any(p in lower for p in _CONVERSATIONAL_PATTERNS):
        return True
    # Questions about self
    if lower.startswith(("who ", "what ", "how ")) and "you" in lower and len(lower) < 60:
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def process_message(
    message: str,
    *,
    session: Session | None = None,
    include_screen: bool = False,
    no_think: bool = True,
    max_tokens: int = 512,
    mode: str = "chat",
) -> str:
    """Run the full Roamin response pipeline and return a reply string.

    This function is the single source of truth for turning a user
    message into a response. Both voice (``wake_listener``) and chat
    (``/chat`` endpoint) call this.

    Args:
        message: User's input text.
        session: Conversation session. If ``None``, ``get_session()`` is called.
        include_screen: Whether to capture a screenshot for tool context.
        no_think: If ``True``, suppress ``<think>`` blocks (faster, shorter).
        max_tokens: Token budget for the reply model.
        mode: ``"chat"`` for the overlay (concise text) or ``"voice"`` (one
              spoken sentence).

    Returns:
        The assistant's reply as a plain string.
    """
    from agent.core.memory import MemoryManager
    from agent.core.model_router import ModelRouter
    from agent.core.voice.session import get_session

    if session is None:
        session = get_session()

    memory = MemoryManager()

    # ── 1. Fact extraction ──
    fact_stored = extract_and_store_fact(message, memory)

    # ── 2. Memory context ──
    memory_context = build_memory_context(message, memory)

    # ── 3. Tool dispatch — direct dispatch first, AgentLoop as fallback ──
    # Use the module-level singleton that has plugins loaded (mempalace_search, etc.)
    loop = _get_chat_loop()
    tool_context = ""

    # ── 3a. MemPalace context — only when explicitly requested ──
    _lower = message.lower()
    _mempalace_triggers = ["palace", "mempalace", "mem palace", "memory search", "search my mem"]
    mempalace_context = ""
    if any(t in _lower for t in _mempalace_triggers):
        # Overview/summary queries → use mempalace_status (returns all entries)
        # Specific topic queries → use mempalace_search (semantic similarity)
        _overview_words = ["what", "show", "list", "contents", "status", "summary", "summarize", "entries"]
        if any(w in _lower for w in _overview_words):
            _mp_result = loop.registry.execute("mempalace_status", {})
            _mp_ok = _mp_result and (_mp_result.get("ok") or _mp_result.get("success"))
            if _mp_ok and _mp_result.get("result"):
                mempalace_context = f"MemPalace contents:\n{str(_mp_result['result'])[:1500]}"
        else:
            mempalace_context = build_mempalace_context(message, loop.registry)

    # ── 3b. Direct dispatch — single-tool requests skip AgentLoop entirely ──
    if not _is_conversational(message):
        tool_context = _try_direct_dispatch(message, loop.registry)

    # ── 3c. AgentLoop — only for multi-step tasks that direct dispatch didn't handle ──
    if not tool_context and not _is_conversational(message):
        result = loop.run(
            message,
            include_screen=include_screen,
            session_context=session.get_context_block(),
        )
        logger.info(
            "AgentLoop status=%s  steps=%d  error=%s",
            result.get("status"),
            len(result.get("steps", [])),
            result.get("error", ""),
        )
        # Collect tool outcomes
        tool_outputs: list[str] = []
        for s in result.get("steps", []):
            if s.get("status") == "executed" and s.get("tool") and s.get("outcome"):
                tool_outputs.append(f"[{s['tool']}]: {s['outcome']}")
        tool_context = "\n".join(tool_outputs)[:1500]

    # ── 4. Build two-layer system prompt ──
    # Layer 1: Task instructions (short, lets model use its training)
    if mode == "voice":
        if tool_context:
            layer1 = (
                "Tool results are provided below. Use them to answer the user directly. "
                "Reply in ONE short spoken sentence. Plain text only.\n\n"
                f"Tool results:\n{tool_context}"
            )
        else:
            layer1 = (
                "Reply in one natural spoken sentence. Plain text only. " "No lists, no narration, no internal state."
            )
    else:
        if tool_context:
            layer1 = (
                "Tool results are provided below. Use them to answer the user directly. "
                "Reply concisely in plain text. No markdown formatting.\n\n"
                f"Tool results:\n{tool_context}"
            )
        else:
            layer1 = "Reply concisely in plain text. No markdown formatting."

    # Layer 2: Roamin sidecar (persona + context — not overriding instructions)
    layer2 = build_sidecar_context(
        memory_context=memory_context,
        mempalace_context=mempalace_context,
        session_context=session.get_context_block(),
    )

    system_content = f"{layer1}\n\n{layer2}"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message},
    ]

    # ── 5. Generate reply via ModelRouter ──
    router = ModelRouter()
    task_type = "default"
    stream_think = not no_think
    if stream_think and task_type not in ("reasoning", "code"):
        task_type = "reasoning"

    reply = router.respond(
        task_type,
        message,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.4,  # Low temp = less hallucination on local models
        no_think=no_think,
        stream_think=stream_think,
    )

    # ── 6. Clean up response ──
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
    reply = re.sub(r"</?[\w]+>", "", reply).strip()
    reply = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", reply)
    reply = re.sub(r"_{1,2}(.+?)_{1,2}", r"\1", reply)
    reply = re.sub(r"^#{1,6}\s+", "", reply, flags=re.MULTILINE)
    reply = re.sub(r"^\s*[-*]\s+", "", reply, flags=re.MULTILINE)
    reply = re.sub(r"\n{3,}", "\n\n", reply).strip()
    reply = re.sub(r"[^\x00-\x7F]+", "", reply).strip()

    if not reply:
        reply = "Got it." if fact_stored else "Done."
        logger.info("ModelRouter returned empty — using fallback")

    logger.info("Reply [%s]: %s", mode, reply[:100])

    # ── 7. Update session ──
    session.add("assistant", reply)

    return reply
