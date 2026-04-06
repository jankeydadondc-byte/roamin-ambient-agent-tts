## Why

When `ctrl+space` fires while the agent is already processing (AgentLoop running or reply being generated), the second keypress is silently dropped — there is no way to abort a running task. `AgentLoop.cancel()` already exists and is checked between steps, but nothing in `wake_listener.py` ever calls it.

## What Changes

- When `ctrl+space` fires while `_wake_lock` is already held (a wake cycle is in progress), call `self._agent_loop.cancel()` instead of silently ignoring the press.
- Speak a brief cancellation phrase ("Got it, stopping.") via cached TTS immediately after cancelling.
- Track an `_is_agent_running` flag (or check `_wake_lock.locked()`) so cancel is only triggered when there is actually an active agent run to cancel, not during STT recording.
- No new public API, no changes to `AgentLoop` itself — only `wake_listener.py`.

## Capabilities

### New Capabilities

- `hotkey-cancel`: Mid-run cancellation triggered by a second `ctrl+space` press while a wake cycle is active.

### Modified Capabilities
<!-- No spec-level requirement changes to existing capabilities -->

## Impact

- **Files modified**: `agent/core/voice/wake_listener.py` only
- **Dependencies**: No new packages; uses existing `keyboard` module and `self._agent_loop.cancel()`
- **Breaking changes**: None — additive logic inside `_on_wake_thread`
