## Why

The Tauri chat overlay (`/chat` endpoint) and the voice wake listener (`_on_wake()`) both process user messages, but they operate on completely separate code paths. Every system added to `_on_wake()` — MemPalace, memory recall, named facts, session context, ProactiveEngine hooks, new tool layers — must be manually re-wired into `control_api.py`'s `/chat` endpoint or the chat overlay silently misses it.

This has already caused real bugs:
- Chat returned "Done." instead of conversational replies (AgentLoop is a task executor, not a responder — the second LLM call was missing)
- Chat had no access to stored named facts or semantic memory ("it doesn't know my favorite color")
- Chat is not wired to MemPalace at all
- Any future capability added to the voice path will silently not exist in chat until someone remembers to duplicate it

The root cause is that the "brain" of Roamin — the pipeline that turns a user message into a grounded, memory-aware, tool-augmented reply — lives inline inside `_on_wake()`, a voice-specific method. It has never been extracted into a callable unit.

## What Changes

- **New file**: `agent/core/chat_engine.py` containing a single public function `process_message(message, ...)` that encapsulates the full Roamin response pipeline:
  - Fact extraction and storage (`_extract_and_store_fact` logic)
  - Memory context building: ChromaDB semantic search + all named facts (MemoryManager)
  - MemPalace search (when registered and available)
  - Direct dispatch (pattern-matched shortcuts)
  - AgentLoop execution with tool collection
  - ModelRouter reply generation with memory + session + tool context injected
  - Session transcript update
- **`agent/core/voice/wake_listener.py`**: `_on_wake()` delegates its message processing to `process_message()` then pipes the returned text to TTS. All existing voice-specific logic (STT, deduplication, cancellation, think-tier classification) remains in `wake_listener` — only the "brain" moves out.
- **`agent/control_api.py`**: The `/chat` endpoint's inline logic is replaced with a single call to `process_message()`. No more manual re-wiring.

## Capabilities

### New Capabilities

- `unified-message-pipeline`: A single, tested callable that represents the full Roamin response pipeline. Both voice and chat routes call it identically. Adding a new capability to the pipeline (new memory layer, new context injection, new tool) automatically applies to both surfaces.

### Modified Capabilities

- `chat-overlay-response`: Chat overlay now receives the same memory-aware, MemPalace-aware, tool-augmented replies as voice. No separate wiring required.
- `voice-wake-response`: Behaviour unchanged externally; internally delegates brain logic to `chat_engine.process_message()`.

## Impact

- **Files created**: `agent/core/chat_engine.py`
- **Files modified**: `agent/core/voice/wake_listener.py`, `agent/control_api.py`
- **Files unchanged**: All tool registry, MemoryManager, MemPalace, ModelRouter, AgentLoop code — `chat_engine` is a composition layer, not a reimplementation
- **Dependencies**: No new packages
- **Breaking changes**: None — the public API of `/chat`, `/ws/events`, and all wake listener behavior is preserved
- **Test surface**: `chat_engine.process_message()` becomes independently unit-testable without mocking TTS, STT, or wake word machinery
