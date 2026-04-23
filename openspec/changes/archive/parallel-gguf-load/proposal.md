# Parallel GGUF Load During STT Recording Window (ENHANCE #1)

**Date:** 2026-04-19
**Status:** Implemented

---

## Why

After the wake word fires, Roamin's current timeline is strictly sequential:

```
[OWW detect] → chime → "yes?" → [STT records 5s] → [text processing] → [GGUF loads ~4.9s] → reply
```

The GGUF model load (~4.9s wall-clock) happens entirely after STT finishes. During the 5-second
STT recording window the GPU sits idle waiting for the user to finish speaking. That is 4.9s of
free time we are not using.

The fix: spawn a background thread immediately after "yes?" is spoken to pre-warm the default
GGUF model. By the time STT finishes + text processing + dispatch attempt complete, the model
is already loaded. The inference call either finds the model ready (saves ~4.9s) or serializes
through the RLock if the pre-warm is still in progress (partial savings, never worse than today).

---

## What Changes

### Single file: `agent/core/voice/wake_listener.py`

A pre-warm thread is spawned inside `_on_wake()` immediately after `tts.speak("yes?")` returns.

```python
# Spawn pre-warm thread during STT window
_prewarm_event = threading.Event()

def _prewarm_default():
    try:
        from agent.core.llama_backend import CAPABILITY_MAP, _REGISTRY
        cap = "chat" if "chat" in CAPABILITY_MAP else "default"
        _REGISTRY.get_backend(cap)
        print("[Roamin] Pre-warm complete", flush=True)
    except Exception as e:
        print(f"[Roamin] Pre-warm failed ({e}) — will load on demand", flush=True)
    finally:
        _prewarm_event.set()

_prewarm_thread = threading.Thread(target=_prewarm_default, daemon=True, name="gguf-prewarm")
_prewarm_thread.start()
```

The event is not awaited — the main thread proceeds through STT, text processing, dispatch, and
prompt building as normal. By the time `router.respond()` calls `_REGISTRY.get_backend()`, the
lock is either free (pre-warm done → cache hit → instant) or held (pre-warm in progress → main
thread blocks briefly for remainder of load — still faster than full sequential load).

### Pre-warm capability selection

Pre-warm targets `"chat"` (the fast conversational path, same model as `"default"` in practice).
If `"chat"` is not in `CAPABILITY_MAP`, falls back to `"default"`. This covers the 95%+ case.

**When the pre-warm is wrong** (user requests explicit model override like "use reasoning for X"):
- The main thread detects the override after transcription
- `router.respond("reasoning", ...)` calls `get_backend("reasoning")`
- If the pre-warm loaded a different model, `ModelRegistry` unloads it and loads the override
- Net result: same latency as today — no regression, just no savings on that request

### Thread safety

`ModelRegistry._lock` is an `RLock`. It already handles concurrent access:
- Pre-warm thread: acquires lock → loads model → releases lock
- Main thread calling `get_backend()`: if lock is free, cache hit returns instantly;
  if lock is held, waits for pre-warm to finish (partial savings vs. full sequential)
- No deadlock possible: RLock is re-entrant, no nested acquire from same thread

---

## Timeline After Fix

```
[OWW detect] → chime → "yes?" → [STT records 5s]  → [text processing] → router.respond()
                                  [GGUF pre-loads ↗] ← parallel            ↑ cache hit (0.0s)
```

Best case (5s STT ≥ 4.9s GGUF load): **~4.9s saved per wake cycle**
Worst case (user speaks immediately, STT < load time): **partial savings, no regression**
Override case: **0s savings, same as today**

---

## Non-Goals

- **Cancelling the pre-warm on override detection.** The pre-warm is fire-and-forget. If the
  wrong model loads, `get_backend()` unloads and reloads. No cancellation mechanism needed.
- **Pre-warming non-default capabilities.** Vision, code, and reasoning are rare enough that
  pre-warming them speculatively would waste VRAM.
- **Multi-model parallelism.** One model in VRAM at a time (ModelRegistry singleton enforces this).

---

## Impact

| File | Change |
|------|--------|
| `agent/core/voice/wake_listener.py` | ~12 lines added to `_on_wake()` after `tts.speak("yes?")` |
| `agent/core/llama_backend.py` | No changes — thread safety already in place |
| `agent/core/model_router.py` | No changes |
