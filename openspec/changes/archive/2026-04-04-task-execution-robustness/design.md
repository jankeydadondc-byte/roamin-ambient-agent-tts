# Design: Task Execution Robustness

## Context

The agent executes voice commands via a two-layer pipeline: direct dispatch for known patterns,
then AgentLoop for open-ended goals. Both layers call `ToolRegistry.execute()` and ultimately
reach `LlamaCppBackend` for LLM inference. The pipeline is linear and single-threaded within a
wake event; the `_wake_lock` and `_agent_running_event` already serialize concurrent presses.

## Goals

- Suppress duplicate transcriptions within a short time window
- Sort AgentLoop plan steps by priority before execution
- Gate task execution on feature dependency availability
- Recover from tool failures via configured fallback chains

## Non-Goals

- Async/await refactor of the execution pipeline
- Persistent task queue across multiple wake events
- Dynamic fallback discovery (fallbacks are statically configured)
- Rollback of completed steps on later-step failure

## Decisions

**D1 — Fingerprint TTL as instance attribute**

`_fingerprint_ttl = 2.0` is stored on the `WakeListener` instance, not as a module constant.
This allows tests to set `listener._fingerprint_ttl = 0` to disable suppression without patching
global state.

*Alternative rejected:* Module-level `_FINGERPRINT_TTL_SECONDS` constant — not testable without
monkey-patching.

**D2 — Priority scoring as a static method on AgentLoop**

`_priority_score(step)` is a `@staticmethod` on `AgentLoop`. It is placed next to the loop that
calls it and is independently testable via `AgentLoop._priority_score(step)` without constructing
a full AgentLoop instance.

*Alternative rejected:* Module-level free function — equally valid but would be inconsistent with
`_classify_task` which is already a method.

**D3 — Feature readiness checks in agent_loop.py, not llama_backend.py**

`_check_feature_ready(capability)` lives in `AgentLoop`. The check is a routing/execution
decision ("should we proceed with this goal?"), not a model-loading decision. `llama_backend.py`
already validates model paths at load time (module-level constants set to `None` when file
missing). Adding a second gate there would duplicate responsibility.

*Alternative rejected:* Adding a `check_ready()` classmethod to `LlamaCppBackend` — tighter
coupling between execution and inference layers.

**D4 — Fallback table in tool_registry.py, not agent_loop.py**

`_TOOL_FALLBACKS` lives in `tool_registry.py` and `execute()` handles fallback. Direct dispatch
in `wake_listener.py` also calls `registry.execute()` directly (lines ~235–324). Placing fallback
logic in `_execute_step()` would protect only AgentLoop calls, leaving direct dispatch
unprotected. `tool_registry.execute()` is the single authoritative execution gate.

*Alternative rejected:* Per-step fallback in `_execute_step()` — would not protect direct dispatch.

**D5 — Extract _execute_single() from execute()**

`execute()` is refactored to call `_execute_single()` for both the primary tool and each fallback.
This avoids recursion and makes each method independently testable.

*Alternative rejected:* Inlining the fallback loop inside `execute()` with the original try/except
block duplicated — creates maintenance burden.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Fingerprint not cleared if `_on_wake` raises unhandled exception | Clear in `_guarded_wake` finally block, not just at end of `_on_wake` |
| 2s TTL suppresses legitimate fast re-ask after STT mishearing | TTL is per-instance; user can re-ask after ~2s; AgentLoop runs are typically 5-30s so window is conservative |
| Step reordering breaks data-order dependencies (write then read) | `write_file`/`move_file`/`delete_file` are HIGH risk and blocked by the existing risk filter before they reach the sorter; `memory_write` is LOW priority but memory writes can safely defer |
| `web_search` fallback to `fetch_url` returns raw HTML | Logged with `fallback_used` key; LLM must summarize from noisier input; acceptable trade-off vs no result |
| `_check_feature_ready` called on every `run()` | Checks are O(1): `importlib.import_module` is cached after first call; `QWEN3_VL_8B_MMPROJ` is a module-level constant evaluated once at import |

## Migration Plan

All changes are additive or internal refactors. No public API surfaces change:

- `WakeListener.__init__` gains 4 new private attributes — no callers affected
- `AgentLoop.run()` gains a new early-return path — callers already handle `status == "failed"`
- `ToolRegistry.execute()` public signature unchanged — `fallback_used` key is additive
- `_execute_single()` is private — not part of any external interface

No database migrations. No config file changes. No startup sequence changes.

## Open Questions

None. All design decisions are resolved.
