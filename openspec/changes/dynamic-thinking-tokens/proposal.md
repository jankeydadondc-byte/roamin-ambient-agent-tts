# Dynamic Thinking Token Limits

**Date:** 2026-04-24
**Status:** PROPOSED
**Combines:** Option A (split thinking_budget / response_budget) +
             Option B (adaptive budgets tied to think-level tiers)

---

## Problem

`_classify_think_level()` returns one `max_tokens` value. That single budget covers
**both** the `<think>` block and the actual answer. On the LOW tier (max_tokens=1500)
the thinking phase routinely consumes 1,200+ tokens, leaving ~300 for the reply.
On HIGH (8192) the model can think endlessly and still produce a long answer.

The result: long thinking → truncated answer (token budget exhausted mid-reply),
or over-long answers when the model has room to ramble.

---

## What Changes

### 1. `_classify_think_level()` → returns 3-tuple

**Before:**
```python
def _classify_think_level(text: str) -> tuple[bool, int]:
    # returns (no_think, max_tokens)
    # Note: the docstring comment on line 140 says LOW=512 — that comment is stale.
    # The actual return value is 1500 (see line 202).
    return True, 150      # OFF
    return False, 1500    # LOW  (docstring says 512 — stale, fix in this PR)
    return False, 2048    # MED
    return False, 8192    # HIGH
```

**After:**
```python
def _classify_think_level(text: str) -> tuple[bool, int, int]:
    # returns (no_think, thinking_budget, response_budget)
    return True,  0,    150   # OFF  — no <think> block; 150 tokens for answer
    return False, 600,  300   # LOW  — 600 think tokens + 300 response = 900 total
    return False, 1200, 500   # MED  — 1200 + 500 = 1700 total
    return False, 4000, 1000  # HIGH — 4000 + 1000 = 5000 total
```

For **llama-cpp** (local GGUF): `max_tokens = thinking_budget + response_budget`.
The combined total is what gets passed to `LlamaCppBackend.chat()`. The split is
enforced via system prompt guidance added per-tier (see §3).

For **Anthropic API** (future, via control_api.py): pass `thinking.budget_tokens =
thinking_budget` and `max_tokens = response_budget` separately — the API natively
supports this split.

### 2. All call-sites unpacking `_classify_think_level()` updated

**Four** call-sites in `wake_listener.py` currently unpack a 2-tuple:

```python
# Line 1028 — AgentLoop bypass precheck
_precheck_no_think, _ = _classify_think_level(transcription)

# Line 1171 — fast-path model routing check
no_think_check, _ = _classify_think_level(transcription)

# Line 1181 — main classification
no_think, think_max_tokens = _classify_think_level(transcription)
```

**Updated:**
```python
# Line 1028
_precheck_no_think, _, _ = _classify_think_level(transcription)

# Line 1171
no_think_check, _, _ = _classify_think_level(transcription)

# Line 1181
no_think, thinking_budget, response_budget = _classify_think_level(transcription)
think_max_tokens = thinking_budget + response_budget  # combined for llama-cpp
```

Also update the debug log line (currently line 1256) to surface both budgets:
```python
print(
    f"[Roamin] Think level: no_think={no_think}, "
    f"thinking_budget={thinking_budget}, response_budget={response_budget}, "
    f"total_tokens={think_max_tokens}, model={task_type}"
)
```

### 3. `_CAPABILITY_MIN_TOKENS` split into two dicts

**Before (single dict, combined total):**
```python
_CAPABILITY_MIN_TOKENS: dict[str, int] = {
    "reasoning": 2048,
    "code":      1024,
    ...
}
```

**After (separate dicts):**
```python
_CAPABILITY_MIN_THINKING: dict[str, int] = {
    "reasoning":           1200,
    "analysis":            1200,
    "ministral_reasoning": 1200,
    "ministral":            600,
    "ministral_vision":     600,
    "code":                 600,
    "heavy_code":          1200,
}

_CAPABILITY_MIN_RESPONSE: dict[str, int] = {
    "reasoning":           400,
    "analysis":            400,
    "ministral_reasoning": 400,
    "ministral":           300,
    "ministral_vision":    300,
    "code":                400,
    "heavy_code":          500,
}
```

Model override path updated accordingly:
```python
if model_override:
    cap_think = _CAPABILITY_MIN_THINKING.get(model_override, 600)
    cap_resp  = _CAPABILITY_MIN_RESPONSE.get(model_override, 300)
    if no_think:
        no_think = False
    thinking_budget  = max(thinking_budget, cap_think)
    response_budget  = max(response_budget, cap_resp)
    think_max_tokens = thinking_budget + response_budget
```

### 4. `tool_context` floor applied to `response_budget` only

**Before:**
```python
if tool_context and think_max_tokens < 200:
    think_max_tokens = 200
```

**After:**
```python
if tool_context and response_budget < 200:
    response_budget  = 200
    think_max_tokens = thinking_budget + response_budget
```

Tool output requires a longer answer, not more thinking. The floor belongs on the
response side.

### 5. `layer1` system prompt updated to match new budgets

The OFF-tier `layer1` currently says **"12 words maximum"** (line 1214). With
`response_budget=150` tokens and no char cap, that instruction contradicts the
budget. Updated:

```python
# OFF-tier (no_think, no tool_context)
layer1 = (
    "Reply in 1-2 direct spoken sentences. "
    "Be concise. Plain text only. No hedging, no lists, no narration."
)
```

The think-tier `layer1` says "exactly 2 spoken sentences" for all think tiers.
Updated to scale with budget:

```python
if thinking_budget <= 600:   # LOW
    sentence_guidance = "Answer in 1-2 spoken sentences."
elif thinking_budget <= 1200:  # MED
    sentence_guidance = "Answer in 2-3 spoken sentences."
else:                          # HIGH
    sentence_guidance = "Answer fully — as many sentences as needed."

layer1 = (
    f"{sentence_guidance} "
    "Start the first word with your answer — no 'Okay', no preamble, no transition. "
    "Be accurate and direct. No markdown, no lists."
)
```

### 6. Per-tier thinking guidance combined into `layer1`

`think_guidance` is built alongside `sentence_guidance` and prepended so the model
calibrates effort to its budget before reading the response instruction:

```python
# think_guidance — effort calibration
if not no_think:
    if thinking_budget <= 600:
        think_guidance = "Think briefly — one short reasoning chain. "
    elif thinking_budget <= 1200:
        think_guidance = "Reason carefully but stay focused. "
    else:
        think_guidance = "Use your full reasoning capability. "
else:
    think_guidance = ""

# Combined layer1 for think-tier (not no_think, not tool_context)
layer1 = (
    f"{think_guidance}{sentence_guidance} "
    "Start the first word with your answer — no 'Okay', no preamble, no transition. "
    "Be accurate and direct. No markdown, no lists."
)
```

`think_guidance` is empty for OFF-tier (no_think=True) so it harmlessly prepends
nothing to the OFF-tier `layer1` built in §5.

---

## Token Budget Table

| Tier | Trigger           | Think | Response | Total | Notes |
|------|-------------------|-------|----------|-------|-------|
| OFF  | default (simple)  | 0     | 150      | 150   | No `<think>` block |
| LOW  | analyze, explain  | 600   | 300      | 900   | One reasoning chain |
| MED  | think hard        | 1200  | 500      | 1700  | Multi-step reasoning |
| HIGH | max effort        | 4000  | 1000     | 5000  | Full depth |

Model capability override minimum (examples):
- `reasoning` capability: min 1200 think + 400 response
- `code` capability: min 600 think + 400 response

---

## Files Changed

| File | Change |
|------|--------|
| `agent/core/voice/wake_listener.py` | `_classify_think_level()` 3-tuple; **all 4 call-sites** updated; split `_CAPABILITY_MIN_*` dicts; tool_context floor on response_budget; layer1 sentence guidance per tier; think_guidance per tier; debug log updated |
| `agent/core/voice/wake_listener.py` (cleanup) | Remove now-dead `_cap_reply_to_sentences()` function and `_split_sentences` import (orphaned by Option B) |
| None else | `ModelRouter.respond()` and `LlamaCppBackend.chat()` signatures unchanged — they receive the pre-combined `max_tokens` |

### Known risk: `_load_user_params()` override

`ModelRouter.respond()` applies `settings.local.json → model_params.max_tokens`
**after** the caller passes `max_tokens`. If a user has set this value, it silently
replaces the computed `thinking_budget + response_budget`.

**Mitigation:** Do not use the generic `model_params.max_tokens` setting for voice
inference. The voice pipeline should pass `max_tokens` only when it has computed the
combined budget, and `_load_user_params()` should skip the override when it detects
the call is from a voice-path context. Implementation: add an optional
`respect_user_params: bool = True` flag to `ModelRouter.respond()`; voice pipeline
passes `respect_user_params=False`. Alternatively, scope the user override to a
voice-specific key (`voice_max_tokens`) rather than the global `max_tokens`.

---

## What Does NOT Change

- `ModelRouter.respond()` signature — still takes one `max_tokens`
- `LlamaCppBackend.chat()` — still takes one `max_tokens`
- `chat_engine.process_message()` — separate code path, not part of voice pipeline
- `agent_loop.py` planning call — separate, not part of this change
- The Anthropic API `thinking.budget_tokens` integration — out of scope; implement
  when an Anthropic-backed path is added to the voice pipeline

---

## Phases

### Phase 1 — Core split (all the above)
Implement the 3-tuple, update all call-sites, split capability dicts, apply
tool-context floor to response_budget, add think_guidance. Single PR.

### Phase 2 — Calibration (after Phase 1 ships)
Run 20+ voice interactions across all tiers. Measure:
- How often does the thinking phase exhaust its budget (`[Roamin done thinking — token
  budget exhausted]` in logs)?
- Are OFF-tier responses too short (model cramped at 150)?
- Are LOW-tier responses completing within 300 response tokens?

Adjust the budget table constants from actual log data.

### Phase 3 — Anthropic API native thinking split (future)
When `control_api.py` gains a voice-inference path backed by the Anthropic API,
pass `thinking_budget` and `response_budget` separately to `client.messages.create()`
with `thinking={"type": "enabled", "budget_tokens": thinking_budget}`.

---

## Edge Case: Think-Budget Exhaustion Mid-Block

When the model exhausts `max_tokens` while still inside a `<think>` block,
`_stream_with_think_print` appends `\n</think>` so the caller's regex can
strip the block cleanly. The resulting reply after stripping is **empty**.
`wake_listener.py` falls back to `"Got it." if fact_stored else "Done."`.

This is acceptable behavior but can be surprising. With the new split budget,
exhaustion during think is less likely (the combined total is larger for MED/HIGH).
The existing log message `[Roamin done thinking — token budget exhausted]` already
signals this in the monitoring terminal. No code change needed; document as known.

## Open Questions

- **OFF-tier response_budget = 150:** Is that enough? Previously it was 150 (just
  bumped from 28). With no thinking overhead, 150 should give ~110 words — enough
  for 2-3 sentences. Monitor in Phase 2.

- **Thinking budget exhaustion handling:** `_stream_with_think_print` already
  appends `\n</think>` when budget runs out mid-think, preventing think-content
  leaking to TTS. No change needed, but worth noting this is the safety net.

- **Should `response_budget` feed back into the verbosity system (smart-verbosity-
  system spec)?** Yes — once smart-verbosity ships, `response_budget` per tier
  should align with the time-budget ceilings. A `normal` verbosity mode (20s ≈ 150
  words ≈ 200 tokens) maps cleanly to LOW-tier response_budget=300 with headroom.
  No immediate action; note the dependency for when smart-verbosity is implemented.
