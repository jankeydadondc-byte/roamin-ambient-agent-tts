# Proposal: Fix UnboundLocalError in wake_listener._on_wake()

## Summary

Add one line to initialize `result = None` in `wake_listener.py` to prevent an UnboundLocalError when direct-dispatch tools (web_search, mempalace_search, etc.) execute without triggering AgentLoop.

## Why It Matters

- **User Impact:** Roamin crashes after speaking a direct-dispatch reply, terminating the voice session
- **Frequency:** Triggered by any query that matches a direct tool pattern (especially "search..." queries)
- **Severity:** Critical — disrupts voice interface usability

## Technical Details

- **Files Modified:** `agent/core/voice/wake_listener.py` (1 line)
- **Lines Added:** 1 (initialization)
- **Lines Removed:** 0
- **Lines Changed:** 0

**Single-line fix:**
```python
# Before line 579, add:
result = None
```

## Why This Works

1. Direct dispatch paths (web_search, mempalace_search, etc.) don't use AgentLoop, so `result` was never set
2. But line 840 assumes `result` exists and calls `.get("blocked_steps", [])`
3. Initializing `result = None` before the conditionals satisfies both paths:
   - Direct dispatch: `result` stays `None`, line 840 returns `[]` via the conditional
   - AgentLoop: `result` is overwritten by `agent_loop.run()`, line 840 extracts blocked_steps normally

## Verification

After fix, test:
```
User: "Search my memories for plugin auto-discovery"
→ No crash after reply is spoken
```

## Rollout

No dependencies. Can be deployed immediately.
