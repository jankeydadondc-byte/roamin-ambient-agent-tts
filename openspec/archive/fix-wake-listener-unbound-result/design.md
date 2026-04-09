# Design: Fix UnboundLocalError in wake_listener._on_wake()

## Problem

When Roamin executes a direct-dispatch tool (e.g. `web_search()`) without invoking AgentLoop, the `result` variable is never initialized. However, after reply generation and TTS playback, line 840 unconditionally tries to access `result.get("blocked_steps", [])`, causing an `UnboundLocalError`.

### Reproduction

User says: "Search my memories for plugin auto-discovery"
→ Roamin dispatches to `web_search()` directly (bypasses AgentLoop)
→ Reply generated and spoken successfully
→ Crash at line 840: `UnboundLocalError: cannot access local variable 'result' where it is not associated with a value`

### Root Cause

Code paths in `_on_wake()`:

| Path | Sets `result`? | Line Range |
|------|---|---|
| Direct dispatch (vision fast-path) | ❌ | 579–638 (returns early) |
| Direct dispatch (non-vision) | ❌ | 643–645 |
| Direct dispatch (failed) | ❌ | 646–653 |
| AgentLoop | ✅ | 664 + 687 |
| Reply generation | Uses `result` | 840 |

**All three direct-dispatch paths skip the `result = {}` initialization at line 664** because that's inside the `if direct_result is None:` block.

## Solution

Initialize `result = None` before the conditional blocks (at the top of the function or before line 579). Then the conditional at line 840 safely checks:
```python
_handle_blocked_steps(result.get("blocked_steps", []) if result else [], memory)
```

When `result` is `None` (direct dispatch), it returns `[]`. When `result` is a dict (AgentLoop), it extracts blocked_steps.

## Implementation

**File:** `agent/core/voice/wake_listener.py`

**Change:** Add `result = None` before line 579 (after tool_context initialization).

```python
578    tool_context = ""
579+   result = None  # ← ADD THIS LINE
580    if direct_result is not None and direct_result.get("success"):
```

This is a minimal, one-line fix that maintains the existing logic:
- Direct paths: `result` stays `None`
- AgentLoop path: `result` is overwritten by `agent_loop.run()`
- Line 840: Safely handles both cases

## Testing

Verify that direct dispatch queries no longer crash after reply generation:
```
User: "Search my memories for plugin auto-discovery"
Expected: Reply spoken, no crash
```

## Risk Assessment

**Risk Level:** Minimal
- Single-line initialization
- No logic changes
- `result` is only read at line 840 and line 717 (within AgentLoop block)
- No impact on AgentLoop path (overwritten immediately)
