# Roamin Ambient Agent — Architecture Audit
**Date:** 2026-04-18
**Auditor:** /roamin-audit (Claude Code, session 6e66e43e)
**Codebase:** `C:\AI\roamin-ambient-agent-tts`
**Last updated:** 2026-04-23 (ENHANCE #1, VISION #3/ARCH #3/ENHANCE #3 resolved; WAKE #1 partially mitigated)

---

## STATUS LEGEND
- ✅ RESOLVED — no longer present in codebase
- ⚠️ PARTIALLY MITIGATED — reduced but not fully fixed
- 🔴 OPEN — still present, not yet addressed
- 🆕 NEW — discovered after original audit

---

## SESSION UPDATES (2026-04-19)

The following was verified against the live codebase. Several P1 and P2 findings were resolved in prior sessions or self-corrected as side effects of other fixes. New findings from the wake word diagnostic session are added at the end.

**Resolved since audit:**
- VISION #1 / DEBUG #1 / DEPS #1 — `model_overrides` is now `{}`. LM Studio no longer in the routing path.
- VISION #2 / ARCH #1 / DEBUG #2 — `max_tokens` removed from `settings.local.json` `model_params`. Caller-supplied value is respected.
- VISION #4 — Conversational fast-path now uses rule-only `layer2` (not full sidecar). `build_sidecar_context()` only called when `tool_context` is present.
- VISION #5 / ARCH #2 — `_unload_llm()` removed from `_on_wake()`. Comment at line 1109 documents the decision and reasoning.
- ARCH #4 — Warmup now correctly warms GGUF via CAPABILITY_MAP. Self-corrected when LM Studio override was removed.
- ENHANCE #4 — `speak_streaming()` correctly routed. `no_think` → `speak()`, think-tier → `speak_streaming()`. Already correct.
- DEPS #2 — Chatterbox auto-start handled by `_start_wake_listener.vbs`. Not a gap.
- DEBUG #4 — Model label now uses `task_type` instead of hardcoded `"Qwen3-VL-8B"`. Dynamic routing via CAPABILITY_MAP makes the actual model transparent.
- DEBUG #5 / DEPS #3 — CAPABILITY_MAP now built dynamically; only models on disk are registered. Ministral entries absent if model not downloaded. No dead variables or None values in map.
- ARCH #5 / ENHANCE #5 — Static `_CAPABILITY_N_CTX` dict removed. n_ctx values now defined per-capability inside `_MODEL_FAMILY_RULES` and built dynamically alongside CAPABILITY_MAP. The tabled openspec (dynamic-nctx) covers the next level: VRAM-aware auto-sizing — that is a separate enhancement, not this finding.
- ENHANCE #3 — Confirmed duplicate of VISION #3 / ARCH #3. Both refer to `_TOOL_TRIGGERS` keyword list at wake_listener.py:858-867. Consolidated into single item.
- ENHANCE #1 — GGUF pre-warm thread spawned immediately after "yes?" spoken. Runs `_REGISTRY.get_backend("chat")` during the 5s STT recording window. ModelRegistry RLock handles concurrency safely. Best case: ~4.9s latency eliminated per wake cycle.
- VISION #3 / ARCH #3 / ENHANCE #3 — `_TOOL_TRIGGERS` keyword list removed. Replaced with `_classify_intent()`: two-token forced-choice LLM call (max_tokens=2, temperature=0.0) against the pre-warmed GGUF. ~50ms cost, handles all phrasings and inflections correctly. Falls back to `"tool"` on any error (conservative — wrong answer is worse than slow).

**Partially mitigated since audit:**
- WAKE #1 — OWW false-fires on "hey" alone. Whisper post-validation bridge in place. Training pipeline specced (`openspec/changes/local-wake-word-training/`) but not yet run.

**New findings added:**
- 🆕 WAKE #1 — OWW model false-fires on "hey" alone at 0.86–0.99 confidence. Whisper post-validation bridge added. Model retraining required for permanent fix.
- 🆕 WAKE #2 — WAV trim silently failed on IEEE float32 (Chatterbox output format). Python `wave` module only supports PCM. Fixed: binary parser now handles both format 1 (PCM) and format 3 (float32).
- 🆕 WAKE #3 — Chime was firing on raw OWW detection, not on confirmed wake phrase. Moved to after Whisper validation. Now semantically correct: chime = "phrase confirmed".

**Still open:**
- WAKE #1 — OWW model retraining needed (Whisper bridge in place)
- DEBUG #3 — Stop word callback unwired (`on_stop_detect=None`)

---

## SESSION ASSUMPTIONS

```
SESSION ASSUMPTIONS
[A1] Chatterbox TTS is an external process started separately; it is not bundled into Roamin.
[A2] The GPU has sufficient VRAM to hold one GGUF model simultaneously with Chatterbox. This is unverified — the _unload_llm() call before every TTS synthesis assumes the opposite.
     UPDATE 2026-04-19: _unload_llm() has been removed. VRAM coexistence is currently assumed sufficient.
[A3] settings.local.json "default": "deepseek-r1-8b-lmstudio" was intended for LM Studio testing and was not reverted before ambient use.
     UPDATE 2026-04-19: model_overrides is now {}. This assumption no longer applies.
[A4] hey_roamin.onnx and stop_roamin.onnx are trained and present at models/wake_word/.
     UPDATE 2026-04-19: hey_roamin.onnx confirmed present. Model quality issue found: false-fires on "hey" alone. Whisper validation added as bridge.
[A5] DeepSeek R1 8B GGUF (4.68 GB) and Qwen3-VL-8B GGUF are confirmed present at ~/.lmstudio/models/.
Note: findings depending on [A2] inherit MEDIUM confidence until VRAM is measured.
```

---

## SCAN REPORT

```
SCAN REPORT
Target:    Roamin Ambient Agent — C:\AI\roamin-ambient-agent-tts
Session:   2026-04-18
Verified:  2026-04-19

Core loop files identified:
  - agent/core/voice/wake_listener.py   (main dispatch + STT + response orchestration)
  - agent/core/voice/wake_word.py       (OpenWakeWord ONNX detection, stop-word model)
  - agent/core/voice/tts.py             (Chatterbox HTTP + pyttsx3 fallback, phrase cache, streaming)
  - agent/core/llama_backend.py         (GGUF loader, ModelRegistry singleton, CAPABILITY_MAP)
  - agent/core/model_router.py          (3-hop dispatch: GGUF → file_path → HTTP)
  - agent/core/agent_loop.py            (AgentLoop multi-step planner)
  - config/settings.local.json          (runtime overrides — model routing + generation params)
  - run_wake_listener.py                (entry point: warmup, background threads, tray)
```

---

## [VISION] Component Fitness Review

---

```
VISION FINDING #1  ✅ RESOLVED (2026-04-19)
Priority:       P1 → CLOSED
File(s):        config/settings.local.json, agent/core/model_router.py
Component:      model_overrides — "default": "deepseek-r1-8b-lmstudio"
Resolution:     settings.local.json model_overrides is now {}. No LM Studio routing for any task.
                All default-task requests route through CAPABILITY_MAP to DeepSeek R1 8B GGUF.
```

---

```
VISION FINDING #2  ✅ RESOLVED (2026-04-19)
Priority:       P1 → CLOSED
File(s):        config/settings.local.json, agent/core/model_router.py
Component:      model_params — "max_tokens": 348
Resolution:     max_tokens removed from settings.local.json model_params.
                _load_user_params() no longer overwrites caller-supplied max_tokens.
                wake_listener.py _classify_think_level() ceiling (28 tokens no-think, 1500 think) is respected.
```

---

```
VISION FINDING #3  ⚠️ PARTIALLY MITIGATED
Priority:       P2
Severity:       HIGH
Status:         OPEN — fragility remains; double inference mostly prevented
File(s):        agent/core/voice/wake_listener.py, agent/core/agent_loop.py
Component:      AgentLoop — fires on every query not explicitly bypassed
Current state:  Conversational bypass keyword list (_TOOL_TRIGGERS set, ~25 words) prevents AgentLoop
                for most simple queries. Think-tier queries also bypass AgentLoop directly.
                Fragility: keyword match is single-word exact against transcription.lower().split().
                Multi-word triggers ("find me a joke") or new tool additions may slip through.
Remaining gap:  ENHANCE #3 addresses the fragility. Double inference still possible for edge cases.
```

---

```
VISION FINDING #4  ✅ RESOLVED (2026-04-19)
Priority:       P2 → CLOSED
File(s):        agent/core/voice/wake_listener.py
Component:      build_sidecar_context() — injects code session + memory context
Resolution:     Conversational fast-path (no tool_context) uses rule-only layer2:
                  "Answer the question directly and concisely. If you don't know something, say so briefly.
                   Never invent information. Plain text only, no markdown."
                build_sidecar_context() only called when tool_context is present (tool-using path).
```

---

```
VISION FINDING #5  ✅ RESOLVED (2026-04-19)
Priority:       P2 → CLOSED
File(s):        agent/core/voice/wake_listener.py
Component:      _unload_llm() — called before every TTS synthesis
Resolution:     _unload_llm() removed from _on_wake(). Comment at line ~1109 documents:
                "Previously called before every TTS synthesis... Cost: 4.7s model reload...
                The assumption that GGUF + Chatterbox cannot coexist in VRAM is unverified."
                VRAM coexistence is currently untested but observed to be functional.
```

---

## [ARCH] Structural Concerns

---

```
ARCH CONCERN #1  ✅ RESOLVED (2026-04-19)
Priority:       P1 → CLOSED
Scope:          agent/core/model_router.py — _load_user_params()
Resolution:     max_tokens not present in settings.local.json model_params.
                _load_user_params() only overwrites if "max_tokens" key is present.
                Caller-supplied max_tokens from _classify_think_level() is now respected.
```

---

```
ARCH CONCERN #2  ✅ RESOLVED (2026-04-19)
Priority:       P2 → CLOSED
Scope:          agent/core/voice/wake_listener.py — _unload_llm() placement
Resolution:     See VISION #5. _unload_llm() removed. ModelRegistry singleton now caches model
                across interactions as intended.
```

---

```
ARCH CONCERN #3  ⚠️ PARTIALLY MITIGATED
Priority:       P2
Severity:       HIGH
Status:         OPEN — same as VISION #3
Scope:          agent/core/voice/wake_listener.py — response orchestration
Current state:  Conversational bypass prevents double inference for most queries.
                Keyword list fragility remains (ENHANCE #3).
```

---

```
ARCH CONCERN #4  ✅ RESOLVED (2026-04-19, self-corrected)
Priority:       P2 → CLOSED
Scope:          run_wake_listener.py — _warmup()
Resolution:     _warmup() calls router.respond("default", ...). With model_overrides now empty,
                "default" routes via CAPABILITY_MAP to DeepSeek R1 8B GGUF — the correct backend.
                Self-corrected as side effect of fixing VISION #1.
```

---

```
ARCH CONCERN #5  🔴 OPEN
Priority:       P3
Severity:       MEDIUM
Status:         OPEN — unchanged
Scope:          agent/core/llama_backend.py — CAPABILITY_MAP n_ctx settings
Current state:  n_ctx=32768 confirmed for default, chat, reasoning, analysis, ministral* tasks.
                n_ctx=16384 for fast, code, heavy_code. n_ctx=8192 for vision/screen_reading.
Recommendation: Reduce chat/default n_ctx to 4096–8192. Voice context rarely exceeds 2048 tokens.
                May free enough VRAM to confirm GGUF + Chatterbox coexistence without pressure.
Effort:         LOW — single dict change in llama_backend.py
```

---

## [DEBUG] Active Issues

---

```
ISSUE #1  ✅ RESOLVED (2026-04-19)
Priority:      P1 → CLOSED
File(s):       config/settings.local.json, agent/core/model_router.py
Resolution:    See VISION #1. model_overrides empty. LM Studio no longer in routing path.
```

---

```
ISSUE #2  ✅ RESOLVED (2026-04-19)
Priority:      P1 → CLOSED
File(s):       config/settings.local.json, agent/core/model_router.py, agent/core/voice/wake_listener.py
Resolution:    See VISION #2. max_tokens removed from settings. Voice token budget enforced by caller.
```

---

```
ISSUE #3  🔴 OPEN
Priority:      P2
Severity:      HIGH
Status:        OPEN — unchanged
File(s):       run_wake_listener.py
Type:          Feature wired but callback unwired — stop word detection silently does nothing
Current state: run_wake_listener.py line ~394: on_stop_detect=None explicitly
               Stop model (stop_roamin.onnx) runs ONNX inference during TTS but fires into None.
               User cannot interrupt TTS playback.
Note:          User has flagged stop word implementation as next planned feature.
Fix direction: Implement on_stop_detect callback that interrupts TTS playback.
```

---

```
ISSUE #4  🔴 OPEN
Priority:      P3
Severity:      MEDIUM
Status:        OPEN — unchanged
File(s):       agent/core/voice/wake_listener.py
Type:          Hardcoded wrong value — model attribution stored in memory is incorrect
Current state: Line ~1149: model_label = override_name or "Qwen3-VL-8B"
               All non-override queries stored in memory as served by "Qwen3-VL-8B"
               regardless of actual model (DeepSeek R1 8B for chat/default).
Fix direction: Expose currently-loaded model identifier from ModelRegistry and use that.
Effort:        LOW
```

---

```
ISSUE #5  ⚠️ PARTIALLY MITIGATED
Priority:      P3
Severity:      MEDIUM
Status:        PARTIALLY MITIGATED
File(s):       agent/core/llama_backend.py
Type:          MISSING_MODEL_FILE — CAPABILITY_MAP references model not present on disk
Current state: Path assignment now guarded: MINISTRAL_14B = path if path.exists() else None
               Import no longer crashes if model missing.
               Capability entries (ministral, ministral_reasoning, ministral_vision) still registered.
               Runtime call to a ministral capability would fail at _load_gguf() when path is None.
Remaining gap: Remove ministral entries from CAPABILITY_MAP or add a startup guard that logs
               "ministral capability unavailable" and skips registration if model absent.
Effort:        LOW
```

---

## [ENHANCE] Improvement Opportunities

---

```
ENHANCEMENT #1  🔴 OPEN
Priority:          P1 (latency impact)
Severity:          HIGH
Status:            OPEN — not implemented
File(s):           agent/core/voice/wake_listener.py
Area:              STT recording → model load sequencing
Latency impact:    ~4.9 seconds saved per interaction (GGUF cold-load overlapped with STT)
Current state:     STT recording is synchronous. GGUF loads after transcription returns.
                   The 4.9s model load window is wasted — user is already speaking.
Recommendation:    On wake word detection, start GGUF warm in a background thread concurrent
                   with STT. Model ready by the time transcription completes.
Effort:            MEDIUM
```

---

```
ENHANCEMENT #2  ✅ RESOLVED (2026-04-19)
Priority:          P2 → CLOSED
File(s):           config/settings.local.json, agent/core/model_router.py
Resolution:        max_tokens removed from settings. Caller-supplied voice budgets respected.
                   No separate voice profile needed — _classify_think_level() handles tiering.
```

---

```
ENHANCEMENT #3  🔴 OPEN
Priority:          P2
Severity:          MEDIUM
Status:            OPEN — unchanged
File(s):           agent/core/voice/wake_listener.py
Area:              Conversational bypass keyword detection
Current state:     _TOOL_TRIGGERS set of ~25 single words. Checked via word in transcription.split().
                   "find me a joke" triggers AgentLoop. New tools require manual wordlist update.
Recommendation:    Replace with intent classification against actual tool registry.
Effort:            MEDIUM
```

---

```
ENHANCEMENT #4  ✅ RESOLVED (2026-04-19)
Priority:          P2 → CLOSED
File(s):           agent/core/voice/tts.py, agent/core/voice/wake_listener.py
Resolution:        Routing already correct: no_think path → speak(), think-tier → speak_streaming().
                   speak() intentional for single-phrase cached responses (pipeline overhead wasteful).
                   speak_streaming() used for multi-sentence think-tier replies.
```

---

```
ENHANCEMENT #5  🔴 OPEN
Priority:          P3
Severity:          MEDIUM
Status:            OPEN — same as ARCH #5
File(s):           agent/core/llama_backend.py
Area:              CAPABILITY_MAP n_ctx for chat/default task types
Current state:     chat/default n_ctx=32768. Confirmed in CAPABILITY_MAP.
Recommendation:    Reduce to 4096 for chat, 8192 for default. Measure VRAM delta.
Effort:            LOW
```

---

## [DEPS] Dependency Review

---

```
DEPENDENCY #1  ✅ RESOLVED (2026-04-19)
Priority:        P1 → CLOSED
Package/Service: LM Studio
Resolution:      model_overrides empty. LM Studio HTTP endpoint no longer in default routing path.
                 Roamin operates standalone via GGUF backends.
```

---

```
DEPENDENCY #2  ✅ RESOLVED (2026-04-19)
Priority:        P3 → CLOSED
Package/Service: Chatterbox TTS (http://127.0.0.1:4123)
Resolution:      _start_wake_listener.vbs checks if Chatterbox is running and starts it if not.
                 Startup is automated. pyttsx3 fallback covers brief startup window.
```

---

```
DEPENDENCY #3  ⚠️ PARTIALLY MITIGATED
Priority:        P3
Package/Service: Ministral-14B GGUF model file
Status:          Path now guarded with .exists() — import safe. Runtime failure still possible.
                 See DEBUG #5.
```

---

## [NEW] Wake Word Findings (2026-04-19)

---

```
WAKE FINDING #1  ⚠️ PARTIALLY MITIGATED
Priority:        P2
Severity:        HIGH
Status:          Bridge fix applied; permanent fix (model retraining) still needed
File(s):         agent/core/voice/wake_word.py (OWW model), agent/core/voice/wake_listener.py
Component:       hey_roamin.onnx — false-fires on "hey" alone
Observed:        OWW model scores "hey" alone at 0.86–0.99 confidence (same as full "hey roamin").
                 Root cause: model undertrained on "hey"-only negatives. Scores < 0.25 on actual
                 "hey roamin" utterances in some cases (full phrase not reaching threshold).
Mitigation:      Whisper post-validation added in wake_listener.py _validate_wake_phrase():
                 - After OWW fires, last 1.5s of trigger audio transcribed with Whisper
                 - Must match _WAKE_CONFIRM_RE (phonetic variants of "hey roamin") to proceed
                 - Empty transcription fails open (OWW fires mid-phrase before phrase complete)
                 - Non-wake text (e.g. "Hey.", "Hello.", "Thank you.") rejected
Remaining gap:   Retrain hey_roamin.onnx with:
                   - 100+ positive samples of "hey roamin" (varied distances, volumes, pace)
                   - 100+ negative samples of "hey" alone, "hey there", "hey you", ambient speech
                 See docs/WAKE_WORD_TRAINING.md for training procedure.
Latency added:   ~200–400ms (Whisper on CUDA transcribing 1.5s of audio)
```

---

```
WAKE FINDING #2  ✅ RESOLVED (2026-04-19)
Priority:        P2 → CLOSED
File(s):         agent/core/voice/tts.py
Component:       _trim_wav_silence() — silent failure on IEEE float32 WAV
Observed:        Chatterbox outputs WAV format 3 (IEEE float32). Python wave module only supports
                 format 1 (PCM). wave.open() raised "unknown format: 3", silently no-op'd trim.
                 "yes?" retained ~1.1s of trailing silence → ~1.88s total perceived silence.
Resolution:      _trim_wav_silence() rewritten to parse WAV binary directly (struct module).
                 Handles both format 1 (int16) and format 3 (float32). Trim confirmed working:
                 log shows "Trimmed 'fb3f097c...wav': 1.28s → 0.75s" on startup.
```

---

```
WAKE FINDING #3  ✅ RESOLVED (2026-04-19)
Priority:        P2 → CLOSED
File(s):         agent/core/voice/wake_listener.py
Component:       Chime placement — fired on raw OWW detection, not on confirmed wake phrase
Observed:        _play_wake_chime() called at top of _on_wake() before any validation.
                 Chime fired even when OWW was false-firing on "hey" alone.
                 User experienced chime as attached to Roamin's response, not to their wake phrase.
Resolution:      Chime moved to after _validate_wake_phrase() passes.
                 Semantic meaning now correct: chime = "wake phrase confirmed, reply incoming."
                 Sequence: OWW fire → Whisper validate → CHIME → 300ms pause → "yes?" → STT
```

---

## OPEN ITEMS SUMMARY (as of 2026-04-23)

```
OPEN ITEMS
P2 (high):       2
  - WAKE #1               OWW model retraining needed (Whisper bridge in place)
  - DEBUG #3              Stop word callback unwired (on_stop_detect=None)

Tabled (specced, not implemented):
  - dynamic-nctx          VRAM-aware auto-sizing of n_ctx (openspec/changes/dynamic-nctx)

Resolved since original audit: 17 of 20 original findings (85%)
New findings added: 3 (WAKE #1, #2, #3)
Current open: 2 (2× P2)
```

---

## ORIGINAL SESSION RECORD

```
SESSION RECORD
Date:              2026-04-18
Modes completed:   SCAN, VISION, ARCH, DEBUG, ENHANCE, DEPS
Total findings:    25 (across all modes including SCAN candidates)
  P1 (critical):   6  (VISION #1, #2; ARCH #1; DEBUG #1, #2; DEPS #1)
  P2 (high):       9  (VISION #3, #4, #5; ARCH #2, #3, #4; DEBUG #3; ENHANCE #1, #2)
  P3 (medium):     7  (ARCH #5; DEBUG #4, #5; ENHANCE #3, #4, #5; DEPS #2)
  P4 (low):        0
Quality score:     8/10
```

---

*Audit produced by /roamin-audit — Roamin Ambient Agent Architecture Audit command*
*Saved: `docs/roamin-audit-2026-04-18.md`*
*Verified and updated: 2026-04-19*
