## Why

Currently `tts.speak()` synthesizes the entire reply string as one Chatterbox request before playing any audio — for a 3-sentence reply the user waits several seconds in silence. Splitting the reply into sentences and pipelining synthesis with playback will reduce perceived latency to the time it takes to synthesize the first sentence (~1-2 s), while subsequent sentences play without pause.

## What Changes

- Add `speak_streaming(text)` to `TextToSpeech` that splits the reply into sentence chunks, fires Chatterbox synthesis for chunk N+1 concurrently while chunk N is playing, and plays chunks in order.
- `speak()` remains unchanged — it is the safe single-shot path used for short cached phrases and fallback.
- `wake_listener.py` calls `speak_streaming(reply)` for LLM-generated replies instead of `speak(reply)`.
- Sentence splitting handles common English delimiters (`.`, `?`, `!`) while respecting abbreviations and trailing ellipses.
- pyttsx3 / SAPI fallback path: split into sentences and speak sequentially (no concurrency needed — SAPI is already fast).

## Capabilities

### New Capabilities

- `tts-sentence-pipeline`: Sentence-chunked TTS pipeline — split reply into sentences, synthesize and play each chunk with overlap (synthesis of chunk N+1 starts while chunk N plays).

### Modified Capabilities
<!-- No existing spec-level requirements change -->

## Impact

- **Files modified**: `agent/core/voice/tts.py`, `agent/core/voice/wake_listener.py`
- **Dependencies**: No new packages; uses `concurrent.futures.ThreadPoolExecutor` (stdlib) for background synthesis.
- **Breaking changes**: None — `speak()` API is unchanged; `speak_streaming()` is additive.
- **Constraint**: Chatterbox is a single-process HTTP server — concurrent POSTs may serialize internally; pipeline uses at most 1 background synthesis in flight at a time (prefetch-1 model).
