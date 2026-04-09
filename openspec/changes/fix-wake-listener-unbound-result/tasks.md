# Tasks: Fix UnboundLocalError in wake_listener._on_wake()

## Implementation

- [ ] 1.1 — Add `result = None` initialization before line 579 in `agent/core/voice/wake_listener.py`
- [ ] 1.2 — Test direct dispatch (web_search) without crash: `"Search my memories for ..."`
- [ ] 1.3 — Test AgentLoop path still works: `"What did we talk about before?"`
- [ ] 1.4 — Verify MemPalace tool invocation after fix

## Status

**Blocked Steps:** None

**Notes:**
- This is a minimal one-line fix with no behavioral changes
- All three direct-dispatch paths avoid the initialization at line 664, so they need `result = None` to exist before that conditional
