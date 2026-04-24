# Smart Verbosity System

**Date:** 2026-04-24
**Status:** PROPOSED
**Depends on:** voice-pack-system (StyleTTS2 local inference)
**Combines:** Mode-aware routing (Option A) + Time-budget caps (Option C)

---

## Why

The current approach (Option B — no cap, streaming + stop-word interrupt) is the
right immediate fix: Roamin speaks complete answers and the user interrupts when
they've heard enough. But it has no awareness of *intent*. "What time is it?" and
"Explain quantum entanglement" both get the same generation budget and the same
TTS pipeline, even though one warrants 1 sentence and the other warrants 10.

Without structure, two problems emerge:
1. **Short queries get over-generated.** The model fills its token budget even when
   a single sentence would have been the perfect answer.
2. **Conversation mode has no natural flow.** A back-and-forth conversation needs
   turn-taking cues, not just "speak until stopped."

The Smart Verbosity System adds *intent-aware mode routing* (A) with *time-budget
caps per mode* (C) — so Roamin knows how long to talk before it's natural to pause
and check in.

---

## Core Concept: Verbosity Modes

Four modes. The query classifier picks the mode automatically; user can override
explicitly mid-conversation.

| Mode | Trigger | Time Budget | Sentences | Use Case |
|------|---------|-------------|-----------|----------|
| `brief` | "quick", "short answer", "just tell me" | 8s | 1 | Rapid lookup |
| `normal` | default (no signal) | 20s | 2–3 | Conversational |
| `detailed` | "explain", "walk me through", "in depth" | 45s | unlimited | Complex topics |
| `conversation` | "let's talk", "conversation mode" | turn-based | 1–2 per turn | Back-and-forth |

Time budgets are **estimated** from word count at ~0.13s/word (natural speech pace).
They are soft ceilings: Roamin stops at the last complete sentence before the
budget expires, not mid-word. The stop-word interrupt remains available in all modes.

---

## Time-Budget Cap (Option C integration)

Instead of counting chars or sentences, estimate speaking time and stop at the
last sentence boundary before the budget:

```python
def _cap_to_time_budget(reply: str, budget_seconds: float) -> str:
    """Keep sentences until estimated speaking time hits budget_seconds."""
    WORDS_PER_SECOND = 7.7  # ~150 wpm / 60s * 3 (words per token avg)
    sentences = _split_sentences(reply)
    kept, elapsed = [], 0.0
    for s in sentences:
        duration = len(s.split()) / WORDS_PER_SECOND
        if kept and elapsed + duration > budget_seconds:
            break
        kept.append(s)
        elapsed += duration
    return " ".join(kept) if kept else reply
```

This is mode-aware:
- `brief` → 8s budget → ~60 words → 1 sentence
- `normal` → 20s budget → ~150 words → 2-3 sentences
- `detailed` → 45s budget → ~350 words → as many as needed
- `conversation` → 10s budget per turn, but yields after each turn for user response

---

## Mode Classifier

Extend `_classify_think_level()` into `_classify_intent()` that returns both
think level AND verbosity mode:

```python
def _classify_intent(text: str) -> tuple[bool, int, str]:
    """Returns (no_think, max_tokens, verbosity_mode)."""
    ...
```

**Brief triggers** (reduce budget):
- "quick", "briefly", "short answer", "just", "in one sentence",
  "tldr", "tl;dr", "sum up", "bottom line"

**Detailed triggers** (expand budget):
- "explain", "walk me through", "in depth", "in detail", "fully",
  "tell me everything", "elaborate", "break it down", "step by step"

**Conversation mode triggers** (enter turn-taking):
- "let's talk", "conversation mode", "chat mode", "let's have a conversation",
  "talk to me about"

**Exit conversation triggers:**
- "stop conversation", "exit chat", "back to normal", "thanks", "that's enough"

---

## Conversation Mode

Conversation mode changes the interaction model from command→response to
turn-based dialogue:

- Roamin speaks 1–2 sentences, then **pauses and listens** automatically (no
  wake word needed for follow-up)
- Session context accumulates across turns so Roamin remembers the thread
- After 3+ turns of silence, mode resets to normal
- Stop word exits immediately

Implementation: `WakeListener` gets a `_conversation_mode: bool` flag. When set,
after speaking Roamin skips the IDLE transition and re-enters LISTENING directly,
bypassing the wake-word requirement for one turn.

---

## What Changes

### `agent/core/voice/wake_listener.py`

- Replace `_classify_think_level()` with `_classify_intent()` returning 3-tuple
- Add `_cap_to_time_budget(reply, budget_seconds)` helper
- Add `_conversation_mode` flag to `WakeListener`
- Route post-generation reply through `_cap_to_time_budget()` using mode budget
- Add conversation mode loop to `_on_wake()`

### `agent/core/voice/tts.py`

No changes — `speak_streaming()` already handles any reply length correctly.

### `agent/core/model_config.json` (optional)

Add per-mode `max_tokens` overrides so `brief` mode caps inference too, not just
the spoken output:

```json
"verbosity_budgets": {
  "brief":        { "max_tokens": 60,   "tts_seconds": 8  },
  "normal":       { "max_tokens": 150,  "tts_seconds": 20 },
  "detailed":     { "max_tokens": 1500, "tts_seconds": 45 },
  "conversation": { "max_tokens": 100,  "tts_seconds": 10 }
}
```

---

## Phases

### Phase 1 — Time-budget cap, no mode routing (standalone improvement)
1. Add `_cap_to_time_budget()` to `wake_listener.py`
2. Apply `normal` budget (20s) to all replies
3. This is already better than Option B alone — natural stopping point without
   hard sentence counts

### Phase 2 — Mode-aware routing
4. Replace `_classify_think_level()` with `_classify_intent()`
5. Apply per-mode `max_tokens` and TTS budget
6. Brief/normal/detailed modes active

### Phase 3 — Conversation mode (after StyleTTS2 ships)
7. Add `_conversation_mode` flag and auto-listen loop to `WakeListener`
8. Requires fast local TTS (StyleTTS2) so the listen-speak-listen cycle is
   tight enough to feel natural — Chatterbox latency makes conversation mode
   feel broken

---

## Open Questions

- **Words-per-second calibration:** 7.7 w/s is an estimate. Once StyleTTS2 is
  integrated, measure actual playback speed from a sample of baked phrases and
  tune the constant.

- **Detailed mode + stop word UX:** In `detailed` mode, Roamin may speak for 45s
  before the natural end. Stop word is the escape hatch, but should we add a
  mid-reply check-in ("Want me to keep going?") after the normal-mode budget
  expires? Probably too complex for Phase 2 — revisit.

- **Conversation mode context window:** How many turns to keep in context? 6 turns
  (~3 exchanges) is a reasonable default before the context window pressure matters.
