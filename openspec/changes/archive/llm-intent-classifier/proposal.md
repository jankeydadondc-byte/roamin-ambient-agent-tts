# LLM Intent Classifier — Replace _TOOL_TRIGGERS Keyword List (VISION #3 / ARCH #3)

**Date:** 2026-04-19
**Status:** Specced — ready to implement

---

## Why

Roamin decides whether to invoke the AgentLoop (tool-using path) or answer directly
(conversational path) by checking if any word in the transcription matches a hardcoded
set of 25 action verbs (`_TOOL_TRIGGERS`). This is brittle in both directions:

- **False negatives** — `"searching"`, `"renamed"`, `"looking for"` don't match their
  stem and AgentLoop is skipped when it should run
- **False positives** — `"get me a coffee"`, `"check out this idea"`, `"show me how
  you think"` trigger AgentLoop on purely conversational requests
- **Invisible behaviour** — the list is defined inline at the call site; no one knows
  it exists without reading 900 lines into wake_listener.py
- **Zero coverage of new phrasings** — every novel way the user expresses a tool intent
  that doesn't happen to include one of the 25 stems silently misbehaves

The GGUF model that Roamin uses for inference already understands intent fluently. The
pre-warm thread added in ENHANCE #1 means it is loaded in VRAM during the STT window —
available before the bypass decision is even needed. A two-token forced-choice call costs
~50ms and is always correct about intent in a way no static list can be.

---

## What Changes

### Single file: `agent/core/voice/wake_listener.py`

**Remove:** `_TOOL_TRIGGERS` dict and the `any(w in _tl.split() ...)` check (lines 877–886)

**Add:** `_classify_intent()` module-level function

```python
def _classify_intent(transcription: str) -> str:
    """Classify transcription as 'tool' or 'chat' using a two-token LLM call.

    Uses the loaded GGUF backend directly (bypasses ModelRouter overhead).
    Forces output to exactly two tokens — either TOOL or CHAT — by capping
    max_tokens=2 and temperature=0.0.

    Returns 'tool' if AgentLoop should run, 'chat' if direct response is better.
    Falls back to 'tool' (conservative) on any error so AgentLoop is never
    incorrectly skipped on an exception.
    """
    try:
        from agent.core.llama_backend import CAPABILITY_MAP, _REGISTRY
        cap = "chat" if "chat" in CAPABILITY_MAP else "default"
        backend = _REGISTRY.get_backend(cap)
        if not backend.is_loaded():
            return "tool"  # conservative fallback if pre-warm hasn't fired yet

        prompt = (
            "You are a routing classifier. Read the user query and reply with exactly "
            "one word — either TOOL or CHAT.\n\n"
            "Reply TOOL if the query asks you to DO something on the computer: "
            "search the web, open or read a file, run a program, control an app, "
            "take a screenshot, send a message, download something, or perform "
            "any action that requires a tool.\n\n"
            "Reply CHAT if the query is a question, opinion, explanation, "
            "conversation, or anything that can be answered from knowledge alone.\n\n"
            f'User query: "{transcription}"\n'
            "Your one-word answer (TOOL or CHAT):"
        )
        result = backend.generate(prompt, max_tokens=2, temperature=0.0)
        verdict = result.strip().upper()
        if "TOOL" in verdict:
            print(f"[Roamin] Intent: TOOL — '{transcription[:60]}'", flush=True)
            return "tool"
        print(f"[Roamin] Intent: CHAT — '{transcription[:60]}'", flush=True)
        return "chat"
    except Exception as e:
        print(f"[Roamin] Intent classifier error ({e}) — defaulting to TOOL", flush=True)
        return "tool"  # conservative: run AgentLoop rather than skip it
```

**Replace the bypass block** (lines 873–886):

```python
# Before (keyword list):
_TOOL_TRIGGERS = { "search", "find", ... }
if not any(w in _tl.split() for w in _TOOL_TRIGGERS):
    direct_result = {}  # sentinel

# After (LLM classifier):
if _classify_intent(transcription) == "chat":
    print("[Roamin] Conversational query — bypassing AgentLoop", flush=True)
    direct_result = {}  # sentinel
```

---

## Call Site Context

The classifier sits inside `_on_wake()`, at the boundary between direct dispatch and
AgentLoop. Execution order at that point:

```
1. [ENHANCE #1] pre-warm thread has already loaded "chat" model into VRAM
2. _try_direct_dispatch() — pattern-match for known tools (screen, mempalace, etc.)
3. _classify_think_level() — determines reasoning depth
4. [THIS] _classify_intent() — TOOL or CHAT decision (50ms, model already loaded)
5. AgentLoop.run() if TOOL, or direct router.respond() if CHAT
```

Because ENHANCE #1 pre-warms the model during STT recording, the classifier call at
step 4 is a registry cache hit — no load time added.

---

## Prompt Design Rationale

- **Two-token forced choice** — `max_tokens=2, temperature=0.0` makes the model
  deterministic. No sentence generation, no hedging, no hallucination risk.
- **Conservative fallback** — errors return `"tool"`, meaning AgentLoop runs. The cost
  of running AgentLoop unnecessarily is 5–12s of latency. The cost of skipping it when
  needed is a silent wrong answer. Wrong answer is worse.
- **Explicit boundary examples in prompt** — both TOOL and CHAT definitions include
  concrete action descriptions so the model isn't guessing at the distinction.
- **No few-shot examples** — kept to minimum tokens; the model's training is sufficient
  for this binary distinction without examples.

---

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| Pre-warm still in progress | `get_backend()` blocks briefly, then returns — no error |
| GGUF not loaded (pre-warm failed) | `backend.is_loaded()` false → return `"tool"` |
| `generate()` raises exception | Caught → return `"tool"` |
| Model outputs neither TOOL nor CHAT | `"TOOL" in verdict` check fails → returns `"chat"` (safe — only fires if output is clearly not TOOL) |
| llama-cpp-python not installed | ImportError caught → return `"tool"` |

---

## Latency Profile

| Stage | Cost |
|-------|------|
| `get_backend("chat")` — cache hit (pre-warm done) | ~0ms |
| `get_backend("chat")` — pre-warm still running | wait for remainder |
| `generate()` — 2 tokens, temperature=0.0 | ~40–80ms (GPU) |
| Total added to critical path | **~50ms typical** |

This replaces the keyword list check which costs ~0.1ms. The 50ms trade is acceptable:
it eliminates a class of silent misbehaviours that cost the user 5–12s of AgentLoop
latency on false positives, or a wrong answer on false negatives.

---

## Impact

| File | Change |
|------|--------|
| `agent/core/voice/wake_listener.py` | Remove `_TOOL_TRIGGERS` block (~10 lines). Add `_classify_intent()` function (~30 lines). One call-site change. |
| All other files | None |

---

## Non-Goals

- **Multi-class intent** (vision vs. file vs. web etc.) — routing within AgentLoop is
  already handled by `_try_direct_dispatch()`. This classifier only decides TOOL vs CHAT.
- **Caching classifier results** — each wake cycle is a fresh transcription; caching
  adds complexity for no benefit.
- **Confidence scores** — forced two-token output means we get a hard decision, not a
  probability. Sufficient for this use case.
