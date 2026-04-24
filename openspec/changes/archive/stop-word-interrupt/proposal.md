# Stop Word Interrupt — State Machine + Threaded Cancel (DEBUG #3)

**Date:** 2026-04-23
**Status:** Specced — ready to implement
**Audit ref:** DEBUG #3

---

## Why

`WakeWordListener` is instantiated in `run_wake_listener.py` with `on_stop_detect=None`:

```python
wake_word = WakeWordListener(
    on_detect=listener._on_wake_thread,
    on_stop_detect=None,  # Wired to TTS cancel in 11.2
)
```

The comment "Wired to TTS cancel in 11.2" is a deferred TODO that was never fulfilled.
`_check_stop_word()` in `wake_word.py` correctly detects the phrase, reaches
`self._on_stop_detect()`, and calls `None`. The feature silently does nothing.

Three compounding issues make this worse than a simple wire-up:

1. **Stop word detection is silenced during TTS playback.** The existing `_speak_paused`
   wrapper calls `wake_word.pause()`, which sets `_paused = True` but leaves
   `_stop_listening_active = False`. The detection loop gates stop word checks on
   `_stop_listening_active` — so while Roamin is speaking, "stop roamin" is never heard.
   The correct methods — `start_stop_listening()` / `stop_stop_listening()` — already
   exist on `WakeWordListener` and set both flags correctly. The wrapper calls the
   wrong one.

2. **`winsound.PlaySound` is a blocking call.** `_play_wav` issues
   `winsound.PlaySound(str(path), winsound.SND_FILENAME)` which blocks the calling
   thread until playback completes. The correct Windows API interrupt is
   `winsound.PlaySound(None, winsound.SND_PURGE)` issued from a separate thread.

3. **pyttsx3/SAPI fallback paths are entirely uninterruptible.** Both `speak()` and
   `speak_streaming()` fall back to `_speak_pyttsx3()` when Chatterbox is unavailable.
   Because `_on_wake()` runs on a non-main thread, `_speak_pyttsx3()` always routes to
   `_speak_sapi_subprocess()` — a `subprocess.run(timeout=30)` PowerShell call. Stop
   during this path cannot interrupt a running utterance without replacing
   `subprocess.run` with `Popen` + `.kill()` — see Non-Goals.

This spec fixes issues 1 and 2 fully. Issue 3 is mitigated (flag checked before each
call) but not eliminated mid-utterance.

---

## Prerequisite — `stop_roamin.onnx`

`start_stop_listening()` calls `_load_stop_model()` internally. If
`models/wake_word/stop_roamin.onnx` does not exist, `_load_stop_model()` returns
`False`, `_stop_listening_active` is never set, and the entire stop system remains
inert. The wire-up specified here is a no-op until that model is trained.

Training is tracked separately under WAKE #1 /
`openspec/changes/local-wake-word-training/`. This spec is correct to implement now —
it activates automatically once the model file appears.

---

## Design

### State machine

```
IDLE ──wake──► LISTENING ──transcription──► PROCESSING ──result──► SPEAKING
 ▲                  │                            │                      │
 └──────────────────┴──────── stop ─────────────┴──────────────────────┘
```

| State | Active work | Stop behaviour |
|-------|-------------|----------------|
| `IDLE` | Nothing — waiting for trigger | No-op (already stopped) |
| `LISTENING` | STT `record_and_transcribe()` running | `stop_event` set → polling loop exits → `with` block ends → `stream.stop()` drains buffers → `stream.close()`; Whisper skipped |
| `PROCESSING` | `AgentLoop.run()` executing | `agent_loop.cancel()` called → exits at next step boundary; progress speak calls guarded |
| `SPEAKING` | Final TTS reply playing | `winsound.SND_PURGE` issued → playback cut; synthesis executor abandoned non-blocking |

### Signal flow

```
WakeWordListener._check_stop_word()   [audio thread]
    └─► WakeListener._on_stop_word()
            ├─ acquire _state_lock
            ├─ early-exit if state == IDLE
            ├─ self._stop_event.set()
            ├─ self._state = _WakeState.IDLE   # direct — does NOT call _transition_to
            └─ release _state_lock
            ├─ self._tts.stop()                # sets _stop_flag + SND_PURGE
            └─ self._agent_loop.cancel()       # sets _cancel_event
```

### `_stop_flag` ownership

`_stop_flag` lives on `TextToSpeech`. It is:
- **Set** by `tts.stop()` (called from `_on_stop_word()`)
- **Cleared** by `tts.reset_stop()` (called from `_transition_to(IDLE)`)
- **Never cleared inside `speak()` or `speak_streaming()`**

Clearing on IDLE (not SPEAKING) ensures:
1. Every new wake cycle starts with a clean flag — "yes?" always plays
2. Progress phrases during PROCESSING observe the flag as set after stop fires —
   they are skipped at the call site before ever reaching `speak()`
3. The final reply at SPEAKING gets a clean flag because reaching SPEAKING requires
   passing the `if not self._stop_event.is_set()` guard — stop cannot have fired

### What is NOT cancelled

- A tool call already in flight inside `AgentLoop.run()` runs to completion.
- A SAPI subprocess already running in `_speak_sapi_subprocess()` runs to completion
  (up to 30 seconds). Flag is checked before each utterance starts.
- An HTTP synthesis request already running in the executor worker runs to its own
  timeout (~15–33s per attempt). Executor abandoned non-blocking; worker continues
  in background. On Roamin exit immediately after, process may hang up to ~33s.

---

## What Changes

### 1. `agent/core/voice/wake_listener.py`

**Add to module-level imports** (`enum` is not currently imported):

```python
from enum import Enum, auto
```

**Add state enum** (module level, before `WakeListener` class):

```python
class _WakeState(Enum):
    IDLE       = auto()
    LISTENING  = auto()
    PROCESSING = auto()
    SPEAKING   = auto()
```

**Add to `WakeListener.__init__`:**

```python
self._state = _WakeState.IDLE
self._stop_event = threading.Event()
self._state_lock = threading.Lock()   # guards _state; separate from _wake_lock
```

(`threading` is already imported at module level in `wake_listener.py`.)

**Add `_transition_to()` method:**

```python
def _transition_to(self, state: _WakeState) -> None:
    """Move to a new state. Must be called with _state_lock held.

    Clears _stop_event unconditionally on every transition.
    Calls tts.reset_stop() when transitioning to IDLE, ensuring every
    new wake cycle and every explicit early-return starts with a clean
    _stop_flag. This means 'yes?' always plays, and progress phrases
    during PROCESSING observe any active stop signal without it being
    pre-emptively wiped.
    """
    self._state = state
    self._stop_event.clear()
    if state == _WakeState.IDLE and self._tts is not None:
        self._tts.reset_stop()
    print(f"[Roamin] State → {state.name}", flush=True)
```

**Add `_on_stop_word()` method:**

```python
def _on_stop_word(self) -> None:
    """Stop callback — fires when WakeWordListener detects 'stop roamin'.

    Called from the audio thread. Thread-safe via _state_lock.

    Does NOT call _transition_to() — that would clear _stop_event and
    _stop_flag immediately, racing with the threads being signalled.
    _state is set directly; _stop_event and _stop_flag stay set until
    the next _transition_to(IDLE) clears them (at an explicit return in
    _on_wake, or at the start of the next cycle).
    """
    with self._state_lock:
        if self._state == _WakeState.IDLE:
            return  # nothing active — no-op
        print("[Roamin] Stop word detected — cancelling", flush=True)
        self._stop_event.set()
        self._state = _WakeState.IDLE

    try:
        if self._tts is not None:
            self._tts.stop()
    except Exception:
        pass

    try:
        if self._agent_loop is not None:
            self._agent_loop.cancel()
    except Exception:
        pass
```

**Wire state transitions and stop guards in `_on_wake()`:**

**At the very start of `_on_wake()`** — before phrase validation:

```python
def _on_wake(self) -> None:
    # Reset state, _stop_event, and _stop_flag at the start of every cycle.
    # _on_wake() runs under _wake_lock so the previous cycle has fully exited.
    # _transition_to(IDLE) calls tts.reset_stop() — ensures "yes?" always plays
    # even if a previous cycle ended mid-PROCESSING without reaching SPEAKING.
    with self._state_lock:
        self._transition_to(_WakeState.IDLE)
    ...
```

**After `tts.speak("yes?")`, before STT:**

```python
with self._state_lock:
    self._transition_to(_WakeState.LISTENING)

transcription = stt.record_and_transcribe(
    duration_seconds=5,
    stop_event=self._stop_event,
)
```

**After transcription returns** (state LISTENING → PROCESSING):

```python
with self._state_lock:
    if self._stop_event.is_set():
        self._transition_to(_WakeState.IDLE)
        return
    self._transition_to(_WakeState.PROCESSING)
```

**All interim `tts.speak()` / `tts.speak_streaming()` calls must be guarded.** These
fall into two groups — LISTENING state and PROCESSING state — with a layered defence
that handles the window between recording completing and the PROCESSING transition:

- **Primary guard (LISTENING → PROCESSING boundary):** The `stop_event.is_set()` check
  at the transition (shown above) is the first line of defence. If stop fires after STT
  returns but before AgentLoop starts, this catches it and returns immediately — none of
  the PROCESSING speak sites are ever reached.
- **Secondary guard (per call site):** Each speak call is additionally guarded with
  `not self._stop_event.is_set()`. This is defence-in-depth for any stop that fires
  *while* the PROCESSING block is executing (e.g. during a slow AgentLoop step). The
  primary guard alone cannot protect mid-PROCESSING speak calls; the secondary guards
  cannot protect speak calls in LISTENING state since the primary guard hasn't run yet.

Replace the `tts.is_available()` check pattern with:

```python
if tts.is_available() and not self._stop_event.is_set():
    tts.speak("...")   # or tts.speak_streaming("...")
```

**LISTENING state early-return sites (lines 791, 807, 818):** These execute *before*
the PROCESSING transition. The primary guard at the transition hasn't run yet, so the
per-site guard is the only defence here.

```python
# Line 791 — empty transcription:
if tts.is_available() and not self._stop_event.is_set():
    tts.speak("Sorry, I didn't catch that.")

# Line 807 — deduplication guard:
if tts.is_available() and not self._stop_event.is_set():
    tts.speak_streaming("Already on it.")

# Line 818 — session reset:
if tts.is_available() and not self._stop_event.is_set():
    tts.speak("Starting fresh. What's up?")
```

**PROCESSING state sites (lines 937, 942, 946, 962, 973, 977):** These execute after
the PROCESSING transition. The primary guard has already passed, so the per-site guards
here are secondary defence against stop firing mid-PROCESSING.

```python
# _progress_handler closure (lines 937, 942, 946):
def _progress_handler(event: dict) -> None:
    phase = event.get("phase")
    if phase == "planning":
        if tts.is_available() and not self._stop_event.is_set():
            tts.speak("Let me think...")
    elif phase == "step_start":
        total = event.get("total_steps", 0)
        step_num = event.get("step", 0)
        if total > 2 and tts.is_available() and not self._stop_event.is_set():
            tts.speak(f"Step {step_num} of {total}.")
    elif phase == "step_done" and event.get("status") == "blocked":
        step_num = event.get("step", 0)
        if tts.is_available() and not self._stop_event.is_set():
            tts.speak(f"Step {step_num} couldn't be completed, it needs approval.")

# Line 962 — AgentLoop exception:
if tts.is_available() and not self._stop_event.is_set():
    tts.speak("I encountered an error processing that command.")

# Line 973 — AgentLoop cancelled:
if tts.is_available() and not self._stop_event.is_set():
    tts.speak("Got it, stopping.")

# Line 977 — AgentLoop blocked:
if tts.is_available() and not self._stop_event.is_set():
    tts.speak("That requires your approval. Check your notifications.")
```

Note: `tts.speak("yes?")` at line 756 is called while state is IDLE (before the
LISTENING transition). `_transition_to(IDLE)` at cycle start calls `reset_stop()`, so
`_stop_flag` is always clear at that point. No guard needed there.

**Vision fast-path** — transition to SPEAKING before the vision reply:

```python
if tts.is_available():
    with self._state_lock:
        if self._stop_event.is_set():
            self._transition_to(_WakeState.IDLE)
            return
        self._transition_to(_WakeState.SPEAKING)
    tts.speak(vision_reply)
    with self._state_lock:
        self._transition_to(_WakeState.IDLE)
return  # vision fully handled
```

**Final reply block** — transition to SPEAKING:

```python
with self._state_lock:
    if self._stop_event.is_set():
        self._transition_to(_WakeState.IDLE)
        return
    self._transition_to(_WakeState.SPEAKING)

if tts.is_available():
    if no_think:
        tts.speak(reply)
    else:
        tts.speak_streaming(reply)

with self._state_lock:
    self._transition_to(_WakeState.IDLE)
```

`self._tts` and `self._agent_loop` are confirmed stored in `WakeListener.__init__`
at lines 525–527.

---

### 2. `agent/core/voice/tts.py`

**Add to module-level imports** (neither is currently at module level):

```python
import threading
from itertools import count
```

**Add module-level counter** (after imports, before class definition):

```python
_play_counter = count(1)   # unique suffix for tts-play-N thread names
```

**Add to `TextToSpeech.__init__`:**

```python
self._stop_flag = threading.Event()
```

**Add `stop()` method:**

```python
def stop(self) -> None:
    """Signal active playback to stop. Sets _stop_flag and issues winsound.SND_PURGE.

    SND_PURGE is immediate, thread-safe, and safe when nothing is playing.
    _stop_flag is NOT cleared here — it survives until reset_stop() is called
    (from _transition_to(IDLE) in WakeListener) so progress speak calls during
    PROCESSING observe it correctly.
    """
    self._stop_flag.set()
    try:
        import winsound
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass
```

**Add `reset_stop()` method:**

```python
def reset_stop(self) -> None:
    """Clear the stop flag. Called by WakeListener._transition_to(IDLE) to
    ensure each new wake cycle and each explicit early-return starts with a
    clean flag — so 'yes?' and post-stop response phrases always play.
    """
    self._stop_flag.clear()
```

**Rewrite `_play_wav()` with side thread + stop poll:**

```python
def _play_wav(self, path: Path) -> None:
    """Play a WAV file. Interruptible via stop().

    Spawns a daemon side thread for the blocking winsound call so this
    method can poll _stop_flag at 50ms intervals. Thread is daemon=True
    so it does not block process exit.
    """
    import winsound

    self._apply_volume()
    play_done = threading.Event()

    def _play() -> None:
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
        except Exception as e:
            print(f"[TTS] playback error: {e}")
        finally:
            play_done.set()   # always fires, even on exception — confirmed by test

    play_thread = threading.Thread(
        target=_play,
        daemon=True,
        name=f"tts-play-{next(_play_counter)}",
    )
    play_thread.start()

    while not play_done.wait(timeout=0.05):
        if self._stop_flag.is_set():
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
            play_done.wait(timeout=0.5)   # brief grace for side thread to observe purge
            return   # stop path — no join

    # Normal completion. play_done fired from finally in the side thread;
    # thread is daemon=True and holds no resources. No join needed — joining
    # would add up to 500ms latency on every cached phrase playback.
```

**`speak()` — do NOT add `_stop_flag.clear()`; add pyttsx3 guard:**

```python
def speak(self, text: str) -> None:
    # _stop_flag is NOT cleared here. It is managed exclusively by stop() and
    # reset_stop(). See design notes in the spec for rationale.
    text = self._apply_pronunciation(text)

    if text in self._phrase_cache:
        wav = self._phrase_cache[text]
        if wav.exists():
            print(f"[TTS] Cache hit: '{text}'")
            self._play_wav(wav)
            return

    if _chatterbox_available():
        self._speak_chatterbox(text)
    elif not self._stop_flag.is_set():
        self._speak_pyttsx3(text)
```

**`_speak_chatterbox()` — guard all three pyttsx3 fallback sites:**

```python
# At each of the three fallback sites:
if not self._stop_flag.is_set():
    self._speak_pyttsx3(text)
```

**`speak_streaming()` — do NOT add `_stop_flag.clear()`; add sentence-level
guards and explicit executor management:**

```python
def speak_streaming(self, text: str) -> None:
    # _stop_flag is NOT cleared here. See speak() note above.
    text = self._apply_pronunciation(text)
    sentences = _split_sentences(text)

    url = _find_chatterbox_url()
    if url is None:
        for sentence in sentences:
            if self._stop_flag.is_set():
                return
            self._speak_pyttsx3(sentence)
        return

    def _synth(sentence: str, idx: int) -> Path | None:
        dest = _TMP_DIR / f"chatterbox_streaming_{idx}.wav"
        if _synthesize_to_file(sentence, url, dest):
            return dest
        return None

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    early_stop = False
    wav_path: Path | None = None

    try:
        future = executor.submit(_synth, sentences[0], 0)

        for i, sentence in enumerate(sentences):
            if self._stop_flag.is_set():
                early_stop = True
                break

            next_future: concurrent.futures.Future | None = None
            if i + 1 < len(sentences):
                next_future = executor.submit(_synth, sentences[i + 1], i + 1)

            try:
                wav_path = future.result()
            except Exception as e:
                print(f"[TTS] Streaming synthesis failed for sentence {i}: {e} — SAPI fallback")
                wav_path = None

            if self._stop_flag.is_set():
                early_stop = True
                break

            if wav_path is not None:
                self._play_wav(wav_path)
                try:
                    wav_path.unlink(missing_ok=True)
                    wav_path = None
                except OSError:
                    pass
            elif not self._stop_flag.is_set():
                self._speak_pyttsx3(sentence)

            future = next_future  # type: ignore[assignment]

    finally:
        if early_stop:
            # Abandon without blocking — in-flight worker exits within its HTTP
            # timeout in the background. See Non-Goals re: exit hang.
            executor.shutdown(wait=False, cancel_futures=True)
            if wav_path is not None:
                try:
                    wav_path.unlink(missing_ok=True)
                except OSError:
                    pass
        else:
            executor.shutdown(wait=True)
```

**Known latency gap — HTTP synthesis during stop:**
If stop fires while `_speak_chatterbox()` is mid-HTTP-request, the HTTP runs to its
own timeout (~15–33s per attempt, up to 66s with retry). After it completes, `_play_wav`
exits immediately because `_stop_flag` is set. Stop is effective but delayed. HTTP
request cancellation is out of scope.

---

### 3. `agent/core/voice/stt.py`

**Add to module-level imports** (`time` is not currently imported):

```python
import time
```

**Add `stop_event` parameter to `record_and_transcribe()`:**

```python
def record_and_transcribe(
    self,
    duration_seconds: int = 5,
    stop_event: threading.Event | None = None,
) -> str | None:
```

**VAD path — replace blocking `done_event.wait(timeout=12)` with polling loop:**

```python
# Replace:
#   done_event.wait(timeout=12)
# With:
deadline = time.monotonic() + 12
while not done_event.is_set():
    if stop_event is not None and stop_event.is_set():
        done_event.set()
        break
    if time.monotonic() >= deadline:
        break
    time.sleep(0.05)
```

When the loop exits, the `with sd.InputStream` body finishes and `__exit__` fires.
`__exit__` calls `stream.stop()` (draining stop — waits for pending audio buffers,
~32–200ms depending on PortAudio buffer depth) then `stream.close()`. All audio
captured during the drain is discarded by the pre-Whisper stop check below.

**Skip Whisper when stop fires — add check before transcription:**

```python
# After the with-block exits, before np.concatenate / transcribe:
if stop_event is not None and stop_event.is_set():
    return None   # discard audio; skip 500ms–3s Whisper call
```

**Add `stop_event` param to `_record_fixed()` with bounded watchdog:**

```python
def _record_fixed(
    self,
    duration_seconds: int = 5,
    stop_event: threading.Event | None = None,
) -> str | None:
    ...
    if stop_event is not None:
        def _watchdog() -> None:
            # Bounded — expires naturally after recording ends. No thread leak.
            stop_event.wait(timeout=duration_seconds + 2)
            if stop_event.is_set():
                try:
                    sd.stop()   # safe on idle device — confirmed no exception
                except Exception:
                    pass
        threading.Thread(
            target=_watchdog, daemon=True, name="stt-stop-watchdog"
        ).start()

    sd.wait()
    ...
```

**`_record_paused` wrapper needs no changes** — uses `*args, **kwargs`.

---

### 4. `run_wake_listener.py`

**Replace `on_stop_detect=None`:**

```python
wake_word = WakeWordListener(
    on_detect=listener._on_wake_thread,
    on_stop_detect=listener._on_stop_word,
)
```

**Replace `pause()`/`resume()` with `start_stop_listening()`/`stop_stop_listening()`
in TTS wrappers only:**

```python
def _speak_paused(text: str) -> None:
    wake_word.start_stop_listening()
    try:
        _orig_speak(text)
    finally:
        wake_word.stop_stop_listening()

def _speak_streaming_paused(text: str) -> None:
    wake_word.start_stop_listening()
    try:
        _orig_speak_streaming(text)
    finally:
        wake_word.stop_stop_listening()

# _record_paused unchanged.
```

---

### 5. `agent/core/agent_loop.py` — no changes needed

`AgentLoop.cancel()` already exists and `_cancel_event` is already checked between
steps. `WakeListener` already calls `self._agent_loop.cancel()` at line 587.

---

## Thread Safety

| Operation | Thread | Guard |
|-----------|--------|-------|
| `_state` read/write in `_on_wake()` | Wake thread | `_state_lock` at each transition |
| `_state` read/write in `_on_stop_word()` | Audio thread | `_state_lock` |
| `_stop_event.set()` | Audio thread | `threading.Event` — inherently thread-safe |
| `_stop_event.clear()` (inside `_transition_to`) | Wake thread | `threading.Event` — inherently thread-safe |
| `_stop_event.is_set()` (progress guards) | Wake thread | `threading.Event` — inherently thread-safe |
| `_stop_flag.set()` in `tts.stop()` | Audio thread | `threading.Event` — inherently thread-safe |
| `_stop_flag.clear()` in `tts.reset_stop()` | Wake thread (via `_transition_to(IDLE)`) | Called while `_state_lock` held |
| `_stop_flag.is_set()` in `_play_wav` poll | tts-play-N side thread | `threading.Event` — inherently thread-safe |
| `winsound.SND_PURGE` in `_play_wav` poll | tts-play-N side thread | WinMM — designed for cross-thread use |
| `winsound.SND_PURGE` in `tts.stop()` | Audio thread | Idempotent, safe when nothing playing |
| `agent_loop.cancel()` | Audio thread | `_cancel_event` is a `threading.Event` |

---

## `_stop_event` and `_stop_flag` lifecycle

```
_on_wake() start             → _transition_to(IDLE)    → _stop_event.clear()
                                                        → _stop_flag.clear() via reset_stop()
_transition_to(LISTENING)    →                          → _stop_event.clear()
                                                        → (reset_stop not called — not IDLE)
_transition_to(PROCESSING)   →                          → _stop_event.clear()
_on_stop_word()              → direct _state assign     → _stop_event.SET
                                                        → _stop_flag.SET (via tts.stop())
_transition_to(IDLE) at      →                          → _stop_event.clear()
  any early-return                                      → _stop_flag.clear() via reset_stop()
_transition_to(SPEAKING)     →                          → _stop_event.clear()
                                                        → (reset_stop not called — not IDLE)
                                                        → flag already clean (guard enforced)
next _on_wake() start        → _transition_to(IDLE)    → _stop_event.clear() [safety net]
                                                        → _stop_flag.clear() via reset_stop()
```

`reset_stop()` is called **only on IDLE transitions** — either at the explicit early-return
sites or at the start of the next cycle. Progress speak calls during PROCESSING observe
`_stop_flag.is_set() == True` after stop fires and are skipped at their call sites before
reaching `speak()`. The final reply at SPEAKING gets a clean flag because the guard
`if not self._stop_event.is_set()` before `_transition_to(SPEAKING)` ensures stop
cannot have fired and left `_stop_flag` set.

---

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| Stop fires while already IDLE | `_on_stop_word` acquires lock, sees IDLE, returns immediately |
| Stop fires in LISTENING→PROCESSING gap | `stop_event.is_set()` check at transition catches it |
| Stop fires during any early-return path | `_stop_event` + `_stop_flag` stay set; both cleared at start of next `_on_wake()` via `_transition_to(IDLE)` |
| `tts.stop()` raises | Caught in `_on_stop_word` try/except; agent cancel still fires |
| `agent_loop.cancel()` raises | Caught separately; TTS already stopped |
| `winsound.SND_PURGE` while nothing playing | Silent no-op — confirmed by live test |
| `sd.stop()` on idle device | Silent no-op — confirmed by live test |
| `stop_roamin.onnx` missing | `start_stop_listening()` returns without activating; inert until trained |
| Double stop | Second call: IDLE guard in `_on_stop_word` returns immediately |
| Stop during progress phrase | `_stop_event.is_set()` guard at call site skips the speak entirely |
| Stop during "Got it, stopping." / error phrases | Same guard — phrase suppressed; stop was already acknowledged by silence |
| Stop during HTTP synthesis (pre-playback) | `_stop_flag` set; HTTP runs to timeout (~15–33s/attempt, up to 66s); executor abandoned; `_play_wav` exits immediately when called |
| `speak_streaming()` temp file orphaned on stop | Resolved future's file cleaned up in `finally` |
| `_record_fixed` watchdog when stop never fires | `stop_event.wait(timeout=duration_seconds + 2)` expires naturally |
| Whisper runs on discarded audio | `stop_event.is_set()` check before `transcribe()` skips it |
| Trailing audio during `stream.stop()` drain | `stream.stop()` drains pending buffers (~32–200ms); all captured audio discarded by pre-Whisper stop check |
| Roamin exits immediately after stop mid-synthesis | Process may hang up to ~33s for non-daemon executor worker; see Non-Goals |
| "yes?" silent after prior cancelled cycle | Prevented: `_transition_to(IDLE)` at cycle start calls `reset_stop()`, guaranteeing clean `_stop_flag` before "yes?" |

---

## Impact

| File | Change |
|------|--------|
| `agent/core/voice/wake_listener.py` | Add `from enum import Enum, auto`; add `_WakeState` enum; add `_stop_event`, `_state_lock`, `_transition_to()`, `_on_stop_word()`; add cycle-start reset + LISTENING/PROCESSING/SPEAKING transitions; add `_stop_event.is_set()` guard to 3 LISTENING-state early-return sites (lines 791/807/818) and 6 PROCESSING-state speak sites (lines 937/942/946/962/973/977); add SPEAKING transition to vision fast-path |
| `agent/core/voice/tts.py` | Add `import threading`, `from itertools import count`, `_play_counter`; add `_stop_flag`, `stop()`, `reset_stop()`; rewrite `_play_wav()` with side-thread + poll (no join on normal path); update `speak()` with pyttsx3 guard (no `_stop_flag.clear()`); rewrite `speak_streaming()` with explicit executor + `early_stop` flag (no `_stop_flag.clear()`); add pyttsx3 guards in `_speak_chatterbox()` |
| `agent/core/voice/stt.py` | Add `import time`; add `stop_event` param to `record_and_transcribe()` and `_record_fixed()`; replace `done_event.wait()` with polling loop; add pre-Whisper stop check; add bounded `sd.stop()` watchdog |
| `run_wake_listener.py` | `on_stop_detect=listener._on_stop_word`; replace TTS wrappers with `start_stop_listening()`/`stop_stop_listening()` |
| `agent/core/agent_loop.py` | **No changes** |

---

## Non-Goals

- **Cancelling a mid-flight HTTP/subprocess tool call in AgentLoop** — out of scope
- **Mid-utterance interrupt of `_speak_sapi_subprocess()`** — `subprocess.run(timeout=30)`
  has no Python-side cancellation without `Popen` + `.kill()`. Every pyttsx3 fallback
  routes to SAPI from non-main threads. Flag is checked before each utterance only
- **Non-daemon executor worker on Roamin exit** — if stop fires mid-synthesis and
  Roamin exits immediately, process may hang up to ~33s for the worker. Making executor
  workers daemon requires a custom thread factory. Accepted trade-off
- **`stream.abort()` instead of drain during STT cancel** — not called by `__exit__`;
  overriding `__exit__` is disproportionate for a ~32–200ms drain
- **"Pause" state** — stop means stop, not pause-and-resume
- **Stop word confidence tuning** — threshold set in `WakeWordListener`; unchanged
- **UI feedback on stop** (tray icon state change) — desirable follow-on
- **Stop during Whisper phrase validation** — ~200ms–5s window; not justified
