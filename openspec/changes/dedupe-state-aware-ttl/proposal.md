# Dedupe Protocol — State-Aware TTL

**Date:** 2026-04-24
**Status:** PROPOSED

---

## Problem

The current deduplication system uses a fixed 2.0-second wall-clock TTL
(`_fingerprint_ttl = 2.0`). This means:

- If inference takes 6–10 seconds (common on LOW/MED/HIGH tiers) and the wake
  word fires again at second 3, the TTL has already expired — the duplicate
  query runs a second time in parallel.
- A user who accidentally triggers twice in quick succession during a long
  response gets two simultaneous model calls, two TTS streams racing each other.
- Conversely, a 2.0s TTL suppresses legitimate re-triggers immediately *after*
  a fast OFF-tier reply completes (response in ~1s, user asks again 1.5s later —
  still suppressed even though Roamin is idle).

The root bug: **the TTL window is decoupled from the actual processing cycle.**
The correct suppression window is "while Roamin is not idle" — not an arbitrary
wall-clock duration.

---

## What Changes

### 1. Replace wall-clock TTL with state-gate check

**Before:**
```python
# Lines 885–894  _on_wake()
with self._pending_fingerprint_lock:
    if (
        self._pending_fingerprint == _fp
        and (_now_fp - self._last_fingerprint_time) < self._fingerprint_ttl
    ):
        print(f"[Roamin] Duplicate request suppressed (fp={_fp[:8]})", flush=True)
        ...
        return
    self._pending_fingerprint = _fp
    self._last_fingerprint_time = _now_fp
```

**After:**
```python
# _on_wake() — dedupe block
with self._pending_fingerprint_lock:
    _is_active = self._state not in (_WakeState.IDLE, _WakeState.LISTENING)
    if self._pending_fingerprint == _fp and _is_active:
        print(f"[Roamin] Duplicate suppressed — still processing (fp={_fp[:8]})", flush=True)
        if tts.is_available() and not self._stop_event.is_set():
            tts.speak_streaming("Already on it.")
        with self._state_lock:
            self._transition_to(_WakeState.IDLE)
        return
    self._pending_fingerprint = _fp
```

The state check must read `self._state` under `_state_lock`. Since `_pending_fingerprint_lock`
and `_state_lock` are separate locks, acquire them in a consistent order to avoid
deadlock: always acquire `_state_lock` first, then `_pending_fingerprint_lock`.

Revised block acquiring both locks safely:
```python
# Acquire _state_lock first (consistent order), then _pending_fingerprint_lock
with self._state_lock:
    _current_state = self._state

with self._pending_fingerprint_lock:
    _is_active = _current_state not in (_WakeState.IDLE, _WakeState.LISTENING)
    if self._pending_fingerprint == _fp and _is_active:
        print(f"[Roamin] Duplicate suppressed — still processing (fp={_fp[:8]})", flush=True)
        if tts.is_available() and not self._stop_event.is_set():
            tts.speak_streaming("Already on it.")
        with self._state_lock:
            self._transition_to(_WakeState.IDLE)
        return
    self._pending_fingerprint = _fp
```

> **Note on the state snapshot:** Reading `_current_state` then re-acquiring
> `_state_lock` later is safe. In the worst case, state transitioned between
> the two reads — meaning we either (a) let a borderline duplicate through
> (harmless) or (b) suppress a legitimate re-trigger from a freshly-IDLE state
> (also harmless — "Already on it." is still accurate). The race window is
> microseconds.

### 2. Remove `_fingerprint_ttl` and `_last_fingerprint_time`

These two attributes are no longer needed. Remove from `__init__`:

```python
# DELETE these two lines (currently lines 559–560):
self._fingerprint_ttl = 2.0  # seconds; set to 0.0 in tests to disable
self._last_fingerprint_time: float = 0.0
```

Also remove the `_now_fp = time.perf_counter()` line in `_on_wake()` that
populated `_last_fingerprint_time` (currently line 884).

### 3. Fingerprint clear path stays the same

`_guarded_wake()` already clears `_pending_fingerprint = None` after the wake
cycle completes (lines 678–680). This remains correct — the fingerprint is
cleared on every IDLE transition, so after a full cycle the same query can
be triggered again freely.

No change needed to `_guarded_wake()`.

### 4. Update comment on `_fingerprint_ttl` initializer (now deleted)

The `__init__` comment block becomes:

```python
# Request deduplication — suppress identical transcriptions while a cycle is active.
# Fingerprint is set at the start of _on_wake() and cleared when the cycle returns
# to IDLE. Suppression window = duration of the processing cycle, not a wall-clock TTL.
self._pending_fingerprint: str | None = None
self._pending_fingerprint_lock = threading.Lock()
```

---

## Before / After Behavior

| Scenario | Before (2s TTL) | After (state-aware) |
|---|---|---|
| User triggers again 1s into 8s inference | TTL expired — **runs duplicate** | State=PROCESSING — **suppressed** |
| User triggers again 3s into 8s inference | TTL expired — **runs duplicate** | State=PROCESSING — **suppressed** |
| User asks same question 500ms after Roamin returns to IDLE | Fingerprint match within TTL — **suppressed** | State=IDLE — **allowed** |
| User asks different question during processing | Different fingerprint — allowed | Different fingerprint — allowed |
| User asks same question in a new cycle (after first completes) | Fingerprint cleared — allowed | Fingerprint cleared — allowed |

---

## Files Changed

| File | Change |
|---|---|
| `agent/core/voice/wake_listener.py` | Remove `_fingerprint_ttl`, `_last_fingerprint_time`, `_now_fp`; replace wall-clock check with state-gate check in `_on_wake()`; update `__init__` comment |

---

## What Does NOT Change

- `_make_request_fingerprint()` — SHA-256 normalised hash, unchanged
- `_guarded_wake()` fingerprint clear — already correct
- `_pending_fingerprint_lock` — still used
- `_pending_fingerprint` attribute — still used

---

## Edge Cases

### Stop-word fires during "Already on it." TTS
The duplicate path calls `tts.speak_streaming("Already on it.")` then
`_transition_to(IDLE)`. If a stop-word fires during that 0.5s phrase, `_on_stop_word()`
sets the stop event — `speak_streaming` polls it and cuts out. No issue.

### Both OWW and hotkey fire simultaneously for same query
Two `_on_wake()` calls race. The first acquires `_pending_fingerprint_lock`, sets
the fingerprint, and continues. The second sees the fingerprint match and the
state is already PROCESSING — suppressed. This is the desired behavior.

### Test isolation
Tests that set `_fingerprint_ttl = 0.0` to disable dedup no longer have that
lever. Instead, tests should set `_pending_fingerprint = None` directly before
each call, or inject a mock state of IDLE. The state-based check naturally
passes when `_state` is IDLE, so any test that resets state between calls
gets correct dedup behavior for free.

---

## Phases

### Phase 1 — Core fix (this spec)
Remove TTL fields, replace wall-clock check with state gate. Single PR.

### Phase 2 — Calibration (none needed)
State-aware suppression is self-calibrating — no constants to tune.
