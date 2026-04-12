## 1. Create `agent/core/chat_engine.py`

- [x] 1.1 Create `agent/core/chat_engine.py` with module docstring describing it as the unified message pipeline
- [x] 1.2 Implement `extract_and_store_fact(message: str, memory: MemoryManager) -> bool` — shared logic; stores "my X is Y" patterns as named_fact; returns True if fact was stored
- [x] 1.3 Implement `build_memory_context(message: str, memory: MemoryManager) -> str` — shared logic; searches ChromaDB + fetches all named facts; returns formatted context string
- [x] 1.4 Implement `build_mempalace_context(message: str, registry) -> str` — calls `registry.execute("mempalace_search", {"query": message})`; returns result string or "" on failure/unavailability
- [x] 1.5 Implement `process_message(message: str, *, session=None, include_screen: bool = False, no_think: bool = True, max_tokens: int = 512, mode: str = "chat") -> str`:
  - Calls `get_session()` if session is None
  - Calls `extract_and_store_fact()`
  - Calls `build_memory_context()`
  - Calls `build_mempalace_context()` via AgentLoop's registry instance
  - Calls `AgentLoop().run(message, include_screen=include_screen, session_context=session.get_context_block())`
  - Collects `tool_outputs` from executed steps
  - Builds system prompt with: tool_outputs + memory_context + mempalace_context + session_ctx
  - Calls `ModelRouter().respond()` with mode-appropriate system prompt (voice: short sentence, chat: natural text)
  - Strips `<think>...</think>` tags and non-ASCII from response
  - Calls `session.add("assistant", reply)`
  - Returns reply string (falls back to "Done." only if ModelRouter returns empty)
- [x] 1.6 Add module-level logger: `logger = logging.getLogger(__name__)`
- [x] 1.7 Log AgentLoop status, step count, and final reply (first 100 chars) at INFO level

## 2. Wire `/chat` endpoint to `process_message()`

- [x] 2.1 In `agent/control_api.py`, replace the entire try-block body of `chat_send()` with:
  - `session.add("user", message)`
  - `reply = await asyncio.to_thread(process_message, message, session=session, include_screen=include_screen, mode="chat")`
  - `await _broadcast({"type": "chat_response", "data": {"message": reply}})`
  - `return {"response": reply, "session_id": session.session_id}`
- [x] 2.2 Remove all inline AgentLoop, MemoryManager, ModelRouter, and memory context logic from `chat_send()` — it now lives entirely in `chat_engine`
- [x] 2.3 Import is lazy (inside function body) to avoid circular imports
- [x] 2.4 `/chat` still handles `400` on empty message and `500` on exception

## 3. Wire `wake_listener` shared methods to `chat_engine`

- [x] 3.1 Replace `WakeListener._extract_and_store_fact()` body with delegation to `chat_engine.extract_and_store_fact()`
- [x] 3.2 Replace `WakeListener._build_memory_context()` body with delegation to `chat_engine.build_memory_context()`
- [ ] 3.3 **(Deferred)** Full brain cutover: replace the entire brain section (direct dispatch → ModelRouter) with `process_message()` call. Blocked by voice-specific features deeply interleaved: direct dispatch, vision fast-path, think-tier classification, model override detection. Requires adding those as parameters or separate pre-processing hooks to `process_message()`.
- [ ] 3.4 **(Deferred)** Delete the delegate methods once full cutover is complete

## 4. Tests

- [x] 4.1 Create `tests/test_chat_engine.py`
- [x] 4.2 Test `extract_and_store_fact()`: mock MemoryManager, verify `write_to_memory("named_fact", ...)` called for "my favorite color is blue", not called for "hello"
- [x] 4.3 Test `build_memory_context()`: mock MemoryManager.search_memory() returning docs, mock MemoryStore.get_all_named_facts() returning facts, verify output string contains both
- [x] 4.4 Test `process_message()` with all dependencies mocked: AgentLoop, MemoryManager, ModelRouter — verify correct system prompt construction and return value
- [x] 4.5 Test `process_message()` fallback: ModelRouter returns empty string → returns "Done."
- [x] 4.6 Test `process_message()` with tool outputs: AgentLoop returns step with outcome → outcome appears in system prompt passed to ModelRouter

## 5. Verification

- [x] 5.1 Run `python -m pytest tests/test_chat_engine.py -v` — 18/18 tests pass
- [ ] 5.2 Run Roamin via `launch.py`, send a voice command — reply is spoken correctly (wake_listener path unchanged externally)
- [ ] 5.3 Send a chat message via Tauri overlay — reply is conversational, not "Done."
- [ ] 5.4 Tell Roamin a fact via chat ("my favorite color is blue"), then ask about it ("what is my favorite color") — correct answer returned
- [ ] 5.5 Ask a question requiring a tool via chat ("search for latest Python news") — tool result is used in reply
- [x] 5.6 Run `python -m pytest` full suite — no regressions
