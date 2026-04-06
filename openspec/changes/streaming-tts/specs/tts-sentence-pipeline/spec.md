## ADDED Requirements

### Requirement: Sentence-chunked TTS pipeline

`TextToSpeech` SHALL expose a `speak_streaming(text: str) -> None` method that splits the text into sentence chunks, synthesizes chunk N+1 in a background thread while chunk N is playing, and plays all chunks in order.

#### Scenario: Single sentence reply plays without pipeline overhead

- **WHEN** `speak_streaming` is called with text containing only one sentence
- **THEN** the sentence is synthesized and played identically to `speak()`

#### Scenario: Multi-sentence reply pipelines synthesis with playback

- **WHEN** `speak_streaming` is called with text containing two or more sentences
- **THEN** chunk 1 begins synthesis immediately; chunk 2 synthesis starts while chunk 1 is playing; chunk 2 plays immediately after chunk 1 finishes

#### Scenario: Empty or whitespace-only segments are skipped

- **WHEN** sentence splitting produces a segment of fewer than 4 non-whitespace characters
- **THEN** that segment is silently skipped; remaining sentences are unaffected

#### Scenario: Chatterbox unavailable falls back to sequential pyttsx3

- **WHEN** `speak_streaming` is called and Chatterbox is not reachable
- **THEN** each sentence chunk is spoken via pyttsx3/SAPI in order with no pipeline attempt

#### Scenario: Synthesis failure for one sentence falls back to pyttsx3 for that sentence

- **WHEN** Chatterbox synthesis fails for sentence N during the pipeline
- **THEN** sentence N is spoken via pyttsx3/SAPI and pipeline continues with sentence N+1

### Requirement: Sentence splitter handles common English patterns

The sentence splitter SHALL split on `.`, `?`, and `!` followed by whitespace or end-of-string, while retaining the delimiter at the end of each chunk. It SHALL NOT split on common abbreviations (`Mr.`, `Dr.`, `Mrs.`, `vs.`, `e.g.`, `i.e.`).

#### Scenario: Standard sentence boundary detected

- **WHEN** text is `"Hello. How are you?"`
- **THEN** splits produce `["Hello.", "How are you?"]`

#### Scenario: Abbreviation not treated as boundary

- **WHEN** text is `"Dr. Smith is here."`
- **THEN** splits produce `["Dr. Smith is here."]` (one chunk, not two)

#### Scenario: Ellipsis not split mid-phrase

- **WHEN** text contains `"Wait... okay."`
- **THEN** splits produce `["Wait... okay."]` (the `...` does not create an empty segment)

### Requirement: Call site in wake_listener uses speak_streaming for LLM replies

`wake_listener.py` SHALL call `tts.speak_streaming(reply)` for LLM-generated replies instead of `tts.speak(reply)`. Cached-phrase invocations (e.g., "Got it.", "On it.") SHALL continue using `tts.speak()`.

#### Scenario: LLM reply spoken via streaming pipeline

- **WHEN** the agent loop completes and a reply is generated from the LLM
- **THEN** `speak_streaming(reply)` is called, not `speak(reply)`

#### Scenario: Status acknowledgements use cached speak path

- **WHEN** a short status phrase ("Got it.", "Working on it.") is spoken before or during processing
- **THEN** `speak(phrase)` is called, not `speak_streaming(phrase)`
