## 1. Sentence Splitter

- [x] 1.1 Add `_split_sentences(text: str) -> list[str]` private function in `tts.py` using `re` — splits on `[.?!]+` followed by whitespace or end-of-string, retains delimiter, skips abbreviations (`Mr.`, `Dr.`, `Mrs.`, `vs.`, `e.g.`, `i.e.`)
- [x] 1.2 Add minimum-length guard: drop any segment with fewer than 4 non-whitespace characters after splitting
- [x] 1.3 Add ellipsis guard: collapse runs of `...` so they don't generate empty segments

## 2. Unique Temp File Per Sentence

- [x] 2.1 Update `_speak_chatterbox` (or add a helper) to accept an optional `dest_path: Path` so each sentence can write to a numbered file (e.g., `chatterbox_out_0.wav`, `chatterbox_out_1.wav`) rather than the shared `chatterbox_out.wav`
- [x] 2.2 Clean up per-sentence WAV files after playback (delete or overwrite flag)

## 3. `speak_streaming` Method

- [x] 3.1 Add `speak_streaming(self, text: str) -> None` to `TextToSpeech`
- [x] 3.2 Apply pronunciation fixup and sentence split at entry
- [x] 3.3 If Chatterbox is unavailable, delegate to `_speak_pyttsx3` for each sentence and return
- [x] 3.4 Implement prefetch-1 pipeline: synthesize sentence 0 before loop; enter loop — play current WAV while submitting `executor.submit(_synthesize_to_file, next_sentence, ...)` for next sentence; at end of loop `.result()` the future and play
- [x] 3.5 Wrap synthesis futures in `try/except`: on failure, fall back to pyttsx3 for that sentence only and continue
- [x] 3.6 Use `with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:` to ensure thread cleanup on exceptions

## 4. Wake Listener Integration

- [x] 4.1 In `wake_listener.py`, change the final reply speak call from `tts.speak(reply)` to `tts.speak_streaming(reply)` (the call after the LLM reply is generated, `t_reply` section)
- [x] 4.2 Confirm all short status phrases (e.g., `"Working on it."`, `"Got it."`) still use `tts.speak()` — leave them unchanged

## 5. Tests

- [x] 5.1 Add `tests/test_tts_streaming.py` with a test for `_split_sentences`: standard boundary, abbreviation guard, ellipsis, single sentence, empty string
- [x] 5.2 Add a test for `speak_streaming` with Chatterbox mocked — verify sentence synthesis is called once per sentence in order, playback order matches sentence order
- [x] 5.3 Add a test for `speak_streaming` with Chatterbox unavailable — verify fall-through to pyttsx3 per sentence
- [x] 5.4 Add a test for synthesis failure on sentence N — verify remaining sentences still play (no exception raised)

## 6. Verification

- [x] 6.1 Run `python -m pytest tests/test_tts_streaming.py -v` — all tests pass
- [x] 6.2 Run `python -m flake8 agent/core/voice/tts.py agent/core/voice/wake_listener.py` — no new lint errors
- [ ] 6.3 Manual smoke test: start the agent with Chatterbox running, say a multi-sentence query — verify first sentence plays immediately after synthesis, second sentence follows without gap
- [ ] 6.4 Manual fallback test: stop Chatterbox, trigger a reply — verify SAPI speaks each sentence without error
