## Context

`TextToSpeech.speak()` makes one blocking Chatterbox HTTP POST (up to 33 s timeout for long text) and only plays audio after the full WAV is received. For a typical 2-3 sentence LLM reply (40-80 words via Chatterbox at ~1-2 s/sentence), the user waits the full synthesis time before hearing anything.

Chatterbox (`http://127.0.0.1:4123`) is a local HTTP service. It processes one request at a time. The `_synthesize_to_file` helper already handles retry logic.

`winsound.PlaySound` is synchronous (blocking until WAV finishes). Audio playback of a sentence takes roughly its natural spoken duration.

## Goals / Non-Goals

**Goals:**

- Add `speak_streaming(text)` that reduces perceived latency by playing sentence 1 while sentence 2 is being synthesized.
- Keep `speak()` unchanged — it serves cached phrases and short fallback text.
- Wire `speak_streaming()` into `wake_listener.py` for the LLM reply path.
- Handle edge cases: single-sentence reply, empty segments, Chatterbox unavailable.

**Non-Goals:**

- True token-level streaming from the LLM (that's a model_router concern).
- Interrupting audio mid-sentence on cancel (complex; will be addressed separately).
- Parallelising more than one background synthesis at a time (Chatterbox serializes internally anyway).
- Changing the pyttsx3/SAPI fallback in any substantial way — just split and speak sequentially.

## Decisions

### D1: Prefetch-1 pipeline (play N while synthesising N+1)

**Rationale**: Chatterbox is single-threaded — sending two concurrent POSTs just queues them server-side. Prefetch-1 is the maximum effective overlap. Prefetch-2+ would waste the second slot without saving time.

**Alternative considered**: Parallelise all sentences at once. Rejected — saturates Chatterbox, gains nothing.

### D2: `re`-based sentence splitter, not NLTK

**Rationale**: NLTK adds a non-trivial dependency and tokenizer downloads. The reply domain is short spoken sentences (1-3 sentences, 40-80 words) — a regex split on `[.?!]` followed by whitespace/end is sufficient. Edge cases (Mr., Dr., ellipsis) must be handled.

**Alternative considered**: NLTK `sent_tokenize`. Rejected — dependency overhead not justified.

### D3: `concurrent.futures.Future` for background synthesis

**Rationale**: `ThreadPoolExecutor` with `max_workers=1` gives exactly the prefetch-1 semantics: submit next sentence synthesis, play current sentence (blocking), then `.result()` on the future to get the next WAV path.

**Alternative considered**: `threading.Thread` with `queue.Queue`. More code for the same result; `Future.result()` is cleaner.

### D4: Unique temp file per sentence (not shared `chatterbox_out.wav`)

**Rationale**: Current `_speak_chatterbox` writes to a shared `chatterbox_out.wav`. With pipelined synthesis, sentence N+1 would overwrite the file while sentence N is still playing. Generate filenames with sentence index or UUID.

### D5: Minimum sentence length guard (≥ 4 chars after stripping)

**Rationale**: Splitting "Hello!!! How are you?" on `!` produces empty segments. Skip any segment shorter than 4 chars after stripping punctuation/whitespace.

## Risks / Trade-offs

- **Chatterbox down mid-stream**: If synthesis of sentence 2 fails, fall back to pyttsx3 for remaining sentences.
  - Mitigation: `Future.result()` wrapped in try/except; fallback to `_speak_pyttsx3` per sentence.
- **Race between cancel and playback**: User says cancel while chunk N is playing. `winsound.PlaySound` is not interruptible. Accepted limitation for this change.
- **Thread pool leak**: `shut down executor on exception`. Use `with ThreadPoolExecutor(max_workers=1) as executor:` to ensure cleanup.

## Migration Plan

No data migration. `speak_streaming()` is a new method. `wake_listener.py` changes one call site: `tts.speak(reply)` → `tts.speak_streaming(reply)`. Rollback: revert both files.
