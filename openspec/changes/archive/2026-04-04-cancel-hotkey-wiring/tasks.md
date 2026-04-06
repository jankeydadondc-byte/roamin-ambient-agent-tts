## 1. State Tracking

- [x] 1.1 Add `_agent_running_event = threading.Event()` to `WakeListener.__init__`
- [x] 1.2 In `_on_wake`, set `_agent_running_event` immediately before `agent_loop.run(goal)` call
- [x] 1.3 Wrap `agent_loop.run(goal)` in a `try/finally` block that clears `_agent_running_event` on return or exception

## 2. Cancel Path in `_on_wake_thread`

- [x] 2.1 In `_on_wake_thread`, when `_wake_lock.acquire(blocking=False)` fails, check `_agent_running_event.is_set()` before discarding the press
- [x] 2.2 If `_agent_running_event` is set, call `self._agent_loop.cancel()`
- [x] 2.3 Speak a cancellation phrase in a daemon thread (`threading.Thread(target=lambda: tts.speak("Got it, stopping."), daemon=True).start()`)
- [x] 2.4 Return from the handler immediately (do not acquire lock or start a new wake thread)

## 3. Tests

- [x] 3.1 Add `tests/test_cancel_hotkey.py` with a test that: sets `_agent_running_event`, calls `_on_wake_thread` while lock is held, asserts `cancel()` was called on the mock `AgentLoop`
- [x] 3.2 Add a test that: leaves `_agent_running_event` unset, calls `_on_wake_thread` while lock is held, asserts `cancel()` was NOT called (debounce path preserved)
- [x] 3.3 Add a test that: `_on_wake_thread` is called while lock is NOT held, asserts normal flow (lock acquired, wake thread started)

## 4. Verification

- [x] 4.1 Run `python -m pytest tests/test_cancel_hotkey.py -v` — all tests pass
- [x] 4.2 Run `python -m flake8 agent/core/voice/wake_listener.py` — no new lint errors
- [ ] 4.3 Manual smoke test: start the agent, say a long command, press `ctrl+space` again mid-run — confirm "Got it, stopping." is spoken and agent loop stops
