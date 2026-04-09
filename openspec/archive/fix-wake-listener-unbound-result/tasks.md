# Tasks: Fix UnboundLocalError in wake_listener._on_wake()

## Implementation

- [x] 1.1 — Add `result = None` initialization before line 579 in `agent/core/voice/wake_listener.py`
- [x] 1.2 — Test direct dispatch without crash: confirmed no UnboundLocalError after reply
- [x] 1.3 — AgentLoop path still works: confirmed via "What is the palace status?" and other queries
- [x] 1.4 — MemPalace tool invocation verified: mempalace_search and mempalace_status both routing correctly

## Status

**Complete.** All tasks done. Archived after successful voice testing.

**Additional fixes landed alongside this proposal:**
- mempalace tools now return standard `"result"` key (was returning `"output"` / raw dict)
- Direct dispatch now uses `agent_loop.registry` (plugin-loaded) instead of fresh `ToolRegistry()`
- ContextBuilder accepts injected registry so AgentLoop's plugin tools appear in planning prompts
- Added mempalace-specific patterns to `_try_direct_dispatch` before the broad web_search regex
