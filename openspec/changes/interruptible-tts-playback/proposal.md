# Interruptible TTS Playback

**Date:** 2026-04-24
**Status:** PROPOSED

---

## Why

When the stop word fires, the state machine transitions to IDLE immediately but TTS audio
continues playing for the full duration of the current sentence — 9 to 14 seconds of
orphaned audio that the user cannot interrupt.

Root cause: `_play_wav()` calls `winsound.PlaySound(SND_FILENAME)` in a daemon side thread.
This is a **synchronous** WinMM sound. MSDN is unambiguous:

> *"Sounds played in synchronous mode cannot be stopped using SND_PURGE."*

The polling loop in the calling thread issues `SND_PURGE`, waits 0.5 seconds, and returns —
but `SND_PURGE` silently fails on synchronous sounds. The daemon thread is orphaned and
continues running `PlaySound` to completion. The result: the user says "stop" and Roamin
ignores it for the rest of the sentence.

---

## What Changes

### One file: `agent/core/voice/tts.py`

**Remove the daemon side thread entirely.** The only reason it existed was to make the
blocking `PlaySound` call interruptible. With `SND_ASYNC`, the main thread never blocks
and no side thread is needed.

**Switch to `SND_FILENAME | SND_ASYNC`.** The `SND_ASYNC` flag starts playback and returns
immediately. Crucially, `SND_PURGE` *does* work on sounds started with `SND_ASYNC`, giving
us the real stop capability we need.

**Add `_wav_duration()` module-level helper.** Since `SND_ASYNC` returns before playback
finishes, we need to know how long to wait before the sound naturally ends. This helper
parses the RIFF header to compute exact duration without importing any extra libraries —
`struct` is already imported. It supports both PCM int16 (format 1) and IEEE float32
(format 3, what Chatterbox outputs).

**Poll in the calling thread.** `_play_wav()` runs a 50ms polling loop until
`time.monotonic() >= deadline`. If `_stop_flag` fires before the deadline,
`winsound.PlaySound(None, winsound.SND_PURGE)` stops the async sound immediately.

**Remove `_play_counter` and `from itertools import count`.** These existed only to name
the daemon side thread. With no side thread, they're dead code.

**Add `import time`.** Required for `time.monotonic()` in the polling loop.

---

## New Helper: `_wav_duration()`

```python
def _wav_duration(path: Path) -> float:
    """Return playback duration in seconds by parsing the RIFF header.

    Supports PCM int16 (format 1) and IEEE float32 (format 3, Chatterbox output).
    Returns 30.0 on any parse failure so callers always get a usable deadline.
    """
    try:
        raw = path.read_bytes()
        if len(raw) < 44 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
            return 30.0
        pos = 12
        n_ch, sr, bits = 1, 16000, 16
        data_size = 0
        while pos + 8 <= len(raw):
            cid = raw[pos : pos + 4]
            csz = struct.unpack_from("<I", raw, pos + 4)[0]
            if cid == b"fmt ":
                n_ch = struct.unpack_from("<H", raw, pos + 10)[0]
                sr   = struct.unpack_from("<I", raw, pos + 12)[0]
                bits = struct.unpack_from("<H", raw, pos + 22)[0]
            elif cid == b"data":
                data_size = csz
                break
            pos += 8 + csz + (csz % 2)
        if data_size == 0:
            return 30.0
        bps = sr * n_ch * (bits // 8)
        return data_size / bps if bps > 0 else 30.0
    except Exception:
        return 30.0
```

---

## New `_play_wav()`

```python
def _play_wav(self, path: Path) -> None:
    """Play a WAV file. Immediately interruptible via stop().

    Uses SND_ASYNC so PlaySound returns immediately, then polls _stop_flag
    at 50ms intervals until the sound finishes or stop() fires.
    SND_PURGE works on async sounds — playback stops within one poll cycle.
    """
    import winsound

    self._apply_volume()

    # If stop was already set before we even started, bail immediately.
    if self._stop_flag.is_set():
        return

    duration = _wav_duration(path)
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)

    deadline = time.monotonic() + duration + 0.5  # +0.5s conservative grace for OS scheduler jitter (50ms poll is sufficient in practice)
    while time.monotonic() < deadline:
        if self._stop_flag.is_set():
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
            return
        time.sleep(0.05)
```

---

## Edge Cases

| Case | Behaviour |
|------|-----------|
| `_stop_flag` already set on entry | Returns before `PlaySound` is called — no audio emitted |
| `_stop_flag` fires during Chatterbox synthesis (before `_play_wav` is reached) | `speak_streaming()` already checks the flag between sentences — sentence is skipped entirely |
| RIFF parse fails (corrupt file, network error writing WAV) | `_wav_duration()` returns 30.0 — `_play_wav` waits up to 30.5s then exits naturally; `SND_PURGE` still works if stop fires |
| Very short WAV (< 100ms, e.g. cached "yes?") | `_wav_duration()` returns the real duration; deadline ≈ 0.6s; playback completes normally |
| `SND_PURGE` while nothing playing | No-ops safely — documented WinMM behaviour |
| Non-Windows platform | `winsound` is Windows-only; the import guard already handles this; unchanged |
| Concurrent `_play_wav` calls | WinMM has one async channel — a second `PlaySound(SND_ASYNC)` stops the first. `speak_streaming()` is sequential so this cannot happen during normal speech. If it did, the behaviour (previous sentence cut) is preferable to overlap. |

---

## Impact

| File | Change |
|------|--------|
| `agent/core/voice/tts.py` | Add `import time`, add `_wav_duration()` helper, rewrite `_play_wav()`, remove `from itertools import count`, remove `_play_counter = count(1)` |

No other files require changes. The `stop()` / `reset_stop()` interface is unchanged.
`speak_streaming()` is unchanged — it already checks `_stop_flag` between sentences and
passes control through `_play_wav()`, which now returns immediately on stop.

---

## Non-Goals

- **Cross-sentence interrupt** — if stop fires mid-sentence, `_play_wav` stops that sentence.
  The `speak_streaming()` loop already checks `_stop_flag` at each sentence boundary, so
  pipeline sentences after the current one are also abandoned. Full cross-sentence interrupt
  is already wired.
- **pyttsx3/SAPI interrupt** — the synchronous pyttsx3 path is not addressed here. It is the
  fallback (Chatterbox down) and is rarely hit. A separate spec could tackle it.
- **Orphaned synthesis threads** — if `_stop_flag` fires during Chatterbox HTTP synthesis,
  `speak_streaming()` issues `executor.shutdown(wait=False, cancel_futures=True)` and returns.
  The worker thread exits when the HTTP request times out. This is acceptable and unchanged.

---

## Risk

**Low.** The change is self-contained to one method in one file. The `SND_ASYNC` +
`SND_PURGE` combination is MSDN-documented behaviour for Windows 7 through 11. The
`_wav_duration()` helper has a 30.0 fallback so a bad WAV file cannot cause a hang.
No new threads, no new dependencies.

**Interrupt latency breakdown:** `stop()` already calls `winsound.PlaySound(None, SND_PURGE)`
immediately when it fires. With `SND_ASYNC`, this call *is* the audio stop — latency ≈ 0ms.
The 50ms poll loop in `_play_wav()` then detects `_stop_flag` and returns, unblocking the
calling thread. So: audio stops instantly, `_play_wav()` unblocks within ≤ 50ms. Both paths
are safe and independent.

---

## Implementation Order

1. Add `import time` to module-level imports (alphabetical order: after `threading`, before the third-party block)
2. Add `_wav_duration()` as a module-level function (alongside `_trim_wav_silence`)
3. Rewrite `_play_wav()` — replace daemon-thread approach with async + polling
4. Remove `from itertools import count` and `_play_counter = count(1)`
5. Smoke test: wake word → Roamin speaks → say stop word → confirm audio cuts immediately
