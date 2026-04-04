# Proposal: Task Execution Robustness

## Why

Phase 3 delivered stable streaming TTS, think-tier reasoning, and autonomous model discovery. The
execution pipeline is now functionally complete, but four reliability gaps remain that degrade
daily usability:

1. **Duplicate commands** — Pressing the hotkey twice with the same query within a couple of
   seconds triggers the full pipeline twice. The user hears the wake phrase again, the LLM runs
   again, and TTS fires twice in a row. There is no suppression logic.

2. **Arbitrary step ordering** — The planning LLM returns steps in whatever order it prefers.
   User-visible output steps (notify, open URL) may execute *after* background write steps
   (memory_write, write_file), delaying observable feedback.

3. **Silent mid-run crashes on missing dependencies** — A vision query will attempt screen
   observation, model loading, and multimodal routing before discovering that PIL is not installed
   or the mmproj file is missing. The failure happens deep in the stack, not at the entry point
   where it can be surfaced gracefully.

4. **No tool recovery** — If `web_search` fails (DDGS rate-limit, network error), the agent
   returns an empty result with no attempt to recover. There is no fallback to `fetch_url` or any
   other alternative.

## What Changes

- `wake_listener.py` gains **request deduplication**: a SHA-256 fingerprint of the transcription
  is cached with a 2-second TTL. Identical requests within that window are suppressed with an
  "Already on it." spoken response.

- `agent_loop.py` gains **dynamic step prioritization**: plan steps are sorted by a static
  priority score before execution. HIGH-priority steps (notify, screenshot, open_url) execute
  first; LOW-priority steps (memory_write, write_file) execute last.

- `agent_loop.py` gains **feature readiness checks**: a pre-flight gate runs before screen
  observation and planning. If a required dependency (PIL, mmproj) is missing for the classified
  task type, `run()` returns a structured failure immediately with a TTS-ready error message.

- `tool_registry.py` gains **per-tool fallback chains**: `execute()` is split into
  `execute()` + `_execute_single()`. On primary tool failure, each configured fallback is tried
  in order. The first success is returned with a `fallback_used` key for observability.

## Capabilities

- `request-deduplication` — suppresses identical transcriptions within a configurable TTL
- `step-priority-sort` — reorders plan steps: HIGH → MED → LOW
- `feature-readiness-gate` — pre-flight validation before task execution
- `tool-fallback-chain` — automatic recovery when a primary tool fails

## Impact

**Files modified:**
- `agent/core/voice/wake_listener.py`
- `agent/core/agent_loop.py`
- `agent/core/tool_registry.py`

**Files read (no changes):**
- `agent/core/llama_backend.py` (constants referenced in readiness check)

**No new dependencies.** No breaking changes to any public API.
