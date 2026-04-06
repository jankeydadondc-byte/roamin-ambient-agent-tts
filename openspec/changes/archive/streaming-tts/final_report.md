# Archive: streaming-tts

**Status: ✅ COMPLETE (2026-04-04)**

## Summary

Sentence-chunked TTS synthesis with prefetch-1 pipeline. First sentence now spoken in ~8s (was 15-26s silent wait). Chatterbox + pyttsx3 fallback. VRAM unload before synthesis. Abbreviation masking (Mr., Dr.) + ellipsis handling. 62 tests passing.

## Acceptance checklist

- [x] `_split_sentences()` implemented with abbreviation + ellipsis guards
- [x] Unique temp WAV per sentence; cleanup after playback
- [x] `speak_streaming()` method added to `TextToSpeech`
- [x] Prefetch-1 pipeline: sentence N+1 synthesizes while N plays
- [x] Fallback to pyttsx3 per-sentence if Chatterbox unavailable
- [x] `wake_listener.py` wired to `speak_streaming()` for LLM replies
- [x] `tests/test_tts_streaming.py` — all tests passing
- [x] flake8 + black clean

## Key files

- `agent/core/voice/tts.py` — `speak_streaming`, `_split_sentences`, `_speak_chatterbox`
- `agent/core/voice/wake_listener.py` — wired to `speak_streaming`
- `tests/test_tts_streaming.py`
