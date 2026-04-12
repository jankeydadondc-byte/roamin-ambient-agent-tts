## Context

`wake_listener._on_wake()` is a ~300-line method that does everything: STT, deduplication, fact extraction, memory recall, MemPalace search, direct dispatch, AgentLoop, ModelRouter, TTS, session tracking. The "brain" (everything from fact extraction to the final reply string) is interleaved with voice-specific machinery (STT, TTS, cancellation). There is no seam to extract without refactoring.

`control_api.py`'s `/chat` endpoint currently has a hand-rolled partial copy: it calls AgentLoop, collects outcomes, calls ModelRouter, and injects memory context — but it is already diverged. It does not call MemPalace, does not do think-tier classification, and uses a different system prompt style.

Both surfaces call the same underlying objects (`MemoryManager`, `AgentLoop`, `ModelRouter`, `MemoryStore`) — the opportunity is to hoist that shared sequence into a function both can call.

## Goals / Non-Goals

**Goals:**

- Extract the response pipeline from `_on_wake()` into `agent/core/chat_engine.py:process_message()`
- `process_message()` accepts a plain string message and returns a plain string reply
- `process_message()` is the canonical place for: fact extraction, memory context, MemPalace search, direct dispatch (optional), AgentLoop, ModelRouter
- `wake_listener._on_wake()` calls `process_message()` and passes the result to TTS — no other behaviour changes
- `/chat` endpoint calls `process_message()` and returns the result as JSON — no inline pipeline logic remains
- `process_message()` is independently importable and testable with no TTS/STT/hotkey dependencies

**Non-Goals:**

- Moving STT, TTS, wake word detection, or cancellation into `chat_engine` — these remain in `wake_listener`
- Moving think-tier classification or model override detection in the first pass — these can be passed as parameters later
- Changing any tool, memory, or ModelRouter behaviour
- Streaming token-by-token output (separate concern)

## Decisions

### D1: `process_message()` returns a plain `str`, not a dict

**Rationale**: The reply string is the only thing both consumers need. `wake_listener` feeds it to TTS. `/chat` wraps it in JSON. A `str` return keeps the interface minimal and avoids coupling callers to internal result structure.

**Alternative considered**: Return a rich dict `{reply, tool_outputs, memory_context, session_id}`. Rejected for initial pass — YAGNI. Can be added later if the control panel needs structured metadata.

### D2: Voice-specific features (think-tier, model override, deduplication) stay in `wake_listener`

**Rationale**: `process_message()` must work for chat where none of those concepts exist. Think-tier classification depends on transcription patterns tuned for voice commands. Forcing chat through that path would degrade chat quality.

**Alternative considered**: Pass a `mode: Literal["voice", "chat"]` flag. Possible future extension but premature now — the feature sets are currently too different.

### D3: MemPalace is called via `registry.execute("mempalace_search", ...)` inside `process_message()`, not as a direct import

**Rationale**: MemPalace is a registered tool plugin. Calling it through the registry respects the plugin boundary and means it benefits from any future registry features (timeouts, error wrapping). Direct import would couple `chat_engine` to the MemPalace implementation.

**Alternative considered**: Import `MemPalacePlugin` directly. Rejected — tight coupling to an optional plugin.

### D4: `process_message()` takes an optional `session` parameter; if `None`, it calls `get_session()` internally

**Rationale**: `wake_listener` already holds a `session` reference it passes around. Accepting it as a parameter avoids a second `get_session()` call and makes the function testable with a mock session.

### D5: `wake_listener` keeps its `_extract_and_store_fact` and `_build_memory_context` methods; `chat_engine` reimplements the same logic inline in the first pass

**Rationale**: The wake listener methods are instance methods with `self` and `MemoryManager` parameters in a class that we don't want `chat_engine` to import. In the first pass, duplicate the ~30 lines. In a follow-up, these can be extracted to `agent/core/memory/context.py` as standalone functions and imported by both.

**Alternative considered**: Import `WakeListener` and call its methods statically. Rejected — creates a circular-ish dependency (chat_engine → wake_listener → chat_engine possible in future).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Input Surface                   │
├──────────────────────┬──────────────────────────────────┤
│   Voice (wake word)  │         Chat Overlay             │
│   wake_listener.py   │       control_api.py /chat       │
│                      │                                  │
│  STT → transcription │  HTTP POST → message string      │
│  dedup check         │                                  │
│  think-tier classify │                                  │
│  model override      │                                  │
│         ↓            │              ↓                   │
│   process_message(message, session, include_screen)     │
│         ↑            │              ↑                   │
│  returns reply str   │   returns reply str              │
│         ↓            │              ↓                   │
│  TTS.speak(reply)    │  JSON {response: reply}          │
└──────────────────────┴──────────────────────────────────┘

process_message() internal flow:
  1. Fact extraction  → MemoryManager.write_to_memory()
  2. Memory context   → MemoryManager.search_memory() + MemoryStore.get_all_named_facts()
  3. MemPalace        → registry.execute("mempalace_search", {query})  [if available]
  4. AgentLoop.run()  → collects tool_outputs
  5. ModelRouter      → respond() with system prompt containing:
                        tool_outputs + memory_context + mempalace_hits + session_ctx
  6. Session update   → session.add("assistant", reply)
  returns: reply str
```

## Risks / Trade-offs

- **Behaviour divergence during migration**: While `wake_listener` still has its inline pipeline AND `chat_engine` exists, the two can drift. Mitigation: complete the wake_listener cutover in the same PR — don't let both paths coexist for long.
- **Think-tier quality regression in chat**: Chat currently uses `no_think=True` with `max_tokens=512`. If think-tier is added to `process_message()` later, chat users may see slower responses. Mitigation: `process_message()` accepts `no_think: bool = True` as a parameter; voice passes its classified value, chat defaults to True.
- **MemPalace unavailable**: MemPalace may not be registered in all environments. `registry.execute("mempalace_search")` will return `{"ok": False}` — already handled by try/except pattern.
- **Session threading**: `get_session()` uses a global singleton. Multiple concurrent chat requests share the session. Acceptable for now (same as current state).

## Migration Plan

1. Create `agent/core/chat_engine.py` with `process_message()` — runs in parallel with existing code, no consumers yet
2. Wire `/chat` endpoint to `process_message()` — replaces current inline logic
3. Wire `wake_listener._on_wake()` to `process_message()` — replaces the brain section of `_on_wake()`
4. Delete the duplicated inline code from both callers
5. Rollback: revert steps 2 and 3 independently if regressions appear — `chat_engine.py` itself is safe to leave in place
