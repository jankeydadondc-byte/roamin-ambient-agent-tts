## Context

`WakeListener` uses `_wake_lock` (a non-reentrant `threading.Lock`) to prevent overlapping wake cycles. When `ctrl+space` fires again while the lock is held, `_on_wake_thread` calls `_wake_lock.acquire(blocking=False)`, gets `False`, prints a debounce message, and returns — the second press is silently discarded.

`AgentLoop` already has a complete cancellation mechanism: `_cancel_event = threading.Event()`, `cancel()` sets it, and the execution loop checks it between every step and returns `{"status": "cancelled"}`. However, nothing in `wake_listener.py` ever calls `_agent_loop.cancel()`.

The `_agent_loop` instance is stored as `self._agent_loop` on `WakeListener`, so it is accessible from within `_on_wake_thread`.

## Goals / Non-Goals

**Goals:**

- When `ctrl+space` fires while a wake cycle is active AND the agent loop is running, call `self._agent_loop.cancel()` to stop it between steps.
- Speak an immediate cancellation acknowledgment via TTS so the user hears confirmation.
- Track whether the AgentLoop is currently executing (not just STT or TTS) so spurious cancel presses during voice recording don't fire unnecessarily.

**Non-Goals:**

- Interrupting TTS mid-playback (separate concern — would require TTS streaming).
- Adding a dedicated "cancel" key. The second `ctrl+space` press IS the cancel.
- Changing `AgentLoop.cancel()` itself — it already works.
- Cancelling the model reply generation (LLM inference) — `cancel()` only fires between AgentLoop steps; the model token loop itself is not interrupted.

## Decisions

### D1: Use second `ctrl+space` as cancel (not a separate key)

**Rationale**: No new key binding needed. The existing `_wake_lock` path already detects "already running" — we just change "ignore" to "cancel". Avoids binding a new hotkey and keeps the UX minimal.

**Alternative considered**: Separate `ctrl+c` or `escape` key. Rejected — adds complexity and a second keyboard binding.

### D2: Track `_agent_running` flag, not just `_wake_lock.locked()`

**Rationale**: `_wake_lock` is held for the entire wake cycle including STT and TTS. We only want to invoke `cancel()` when the `AgentLoop.run()` is actually executing — not when the user just started speaking. A boolean `_agent_running` set to `True` just before `agent_loop.run()` and `False` immediately after is more precise.

**Alternative considered**: Always call `cancel()` when lock is held. Simpler but would fire during STT recording and generate wasted work.

### D3: Speak cancellation phrase from cache (non-blocking)

**Rationale**: `tts.speak()` is synchronous — calling it from the cancel path blocks the hotkey thread. Use a cached short phrase or fire it in a new thread. Already established pattern: cache phrases exist at `phrase_cache/`.

## Risks / Trade-offs

- **Race on `_agent_running`**: Set/cleared on the wake thread, read on the hotkey thread — Python GIL protects simple bool assignment, but use `threading.Event` or `threading.Lock` if needed.
  - Mitigation: Use a `threading.Event` (`_agent_running_event`) for safe cross-thread signalling.
- **Cancel after final step**: If all steps are done and AgentLoop is already past the last check, `cancel()` is a no-op — fine.
- **TTS cancel phrase blocked if TTS is busy**: The cancel path should fire the phrase in a daemon thread so the hotkey handler returns immediately.

## Migration Plan

No migration needed. Additive change to a single method in `wake_listener.py`. Rollback: revert the three lines that set/clear `_agent_running_event` and the early-return branch in `_on_wake_thread`.
