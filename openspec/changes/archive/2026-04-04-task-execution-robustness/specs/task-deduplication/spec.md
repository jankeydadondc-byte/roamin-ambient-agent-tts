# Spec: Task Deduplication

## Requirements

### R1 — Identical transcription within TTL is suppressed
If `_on_wake` is called with the same transcription within `_fingerprint_ttl` seconds of the
previous identical transcription, the second call returns early without executing any dispatch,
AgentLoop, LLM, or TTS beyond the suppression message.

### R2 — Suppression message is spoken
When suppressed, the TTS speaks "Already on it." (or skips gracefully if TTS unavailable).

### R3 — Fingerprint cleared after completion
After `_on_wake` completes (or errors), the pending fingerprint is cleared so the same
transcription can be executed again on the next valid press.

### R4 — Different transcription is never suppressed
Two transcriptions that differ in any non-whitespace character produce different fingerprints and
are never suppressed by each other.

### R5 — Whitespace normalized before hashing
"search for  dogs" and "search for dogs" (extra internal space) produce the same fingerprint.

### R6 — TTL configurable per instance
`WakeListener._fingerprint_ttl` can be set to `0.0` to disable suppression in tests.

---

## Scenarios

### Scenario 1: identical request within TTL
```
GIVEN WakeListener._fingerprint_ttl = 2.0
AND _on_wake("search for python tips") is currently executing
WHEN _on_wake("search for python tips") is called again within 2 seconds
THEN the second call returns immediately
AND agent_loop.run() is NOT called a second time
AND TTS speaks "Already on it."
```

### Scenario 2: identical request after TTL expires
```
GIVEN the first _on_wake("search for python tips") completed at t=0
AND _fingerprint_ttl = 2.0
WHEN _on_wake("search for python tips") is called at t=3.0
THEN the second call proceeds normally through the full pipeline
```

### Scenario 3: different transcription not suppressed
```
GIVEN _on_wake("search for dogs") is executing
WHEN _on_wake("search for cats") is called
THEN the fingerprints differ
AND the second call proceeds normally (subject to _wake_lock)
```

### Scenario 4: whitespace normalization
```
WHEN _make_request_fingerprint("search for  dogs") is called
AND _make_request_fingerprint("search for dogs") is called
THEN both return the same SHA-256 hash
```

### Scenario 5: fingerprint cleared after exception
```
GIVEN _on_wake raises an unhandled exception mid-execution
WHEN the exception propagates to _guarded_wake's finally block
THEN the pending fingerprint is cleared
AND the same transcription can execute again on the next press
```
