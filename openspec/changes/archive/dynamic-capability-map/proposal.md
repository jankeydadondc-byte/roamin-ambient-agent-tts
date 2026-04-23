# Dynamic Capability Map

**Date:** 2026-04-19
**Status:** Implemented

---

## Why

`llama_backend.py` currently hardcodes ten model path variables pointing to specific files
on a specific machine. Any model swap, new download, or moved file requires editing source
code. The problem compounds as model exploration continues — every trial model adds more
dead variables and stale paths. The backend already has a `model_scanner.py` that walks
the filesystem and returns structured GGUF metadata; nothing was wiring it to the runtime
routing layer.

The goal: restart Roamin after downloading any GGUF, have it automatically appear under
the right capabilities — no code changes required.

---

## What Changes

- **Remove all hardcoded path variables** from `llama_backend.py` (`QWEN3_VL_8B`,
  `DEEPSEEK_R1_8B`, `MINISTRAL_14B`, `QWEN3_CODER_NEXT`, etc.). Ten path variables and
  four static dicts (`CAPABILITY_MAP`, `_CAPABILITY_N_CTX`, `_MMPROJ_MAP`,
  `_VISION_CAPABILITIES`) replaced with a single discovery function.

- **`_MODEL_FAMILY_RULES`** — a priority-ordered list of rules. Each rule contains:
  - `pattern`: regex matched against the GGUF filename stem
  - `text_caps`: `{capability: n_ctx}` — registered without mmproj
  - `vision_caps`: `{capability: n_ctx}` — registered only when a paired mmproj exists

- **`_build_capability_map()`** — calls `model_scanner.scan_models()` at import time,
  walks the rules in priority order, and builds `CAPABILITY_MAP`, `_CAPABILITY_N_CTX`,
  `_MMPROJ_MAP`, and `_VISION_CAPABILITIES` from whatever is actually on disk. First
  matching model wins each capability; later rules cannot override it.

- **`agent_loop.py`** — removes direct import of `QWEN3_VL_8B_MMPROJ`. Vision
  availability check now uses `CAPABILITY_MAP.get("vision")` + `_MMPROJ_MAP` lookup,
  which is model-agnostic.

- **`tests/test_vision_model.py`** — removes imports of named path constants and the
  hardcoded `"abliterated"` path assertion. Tests now verify that vision capabilities
  exist and resolve correctly without assuming a specific model filename.

---

## Model Family Rules (priority order)

| Priority | Pattern | text_caps | vision_caps |
|----------|---------|-----------|-------------|
| 1 | `deepseek.*r1` | default (32768), chat (32768), reasoning (32768), analysis (32768) | — |
| 2 | `qwen.*\bvl\b` | fast (16384) | vision (8192), screen_reading (8192) |
| 3 | `qwen.*coder \| coder.*next` | code (16384), heavy_code (16384) | — |
| 4 | `ministral` | ministral (32768), ministral_reasoning (32768) | ministral_vision (32768) |
| 5 | `reasoning.*distill \| qwen.*27b` | reasoning (32768), analysis (32768) *(fallback)* | — |

Rules 1–4 cover all current models. Rule 5 is a fallback so that if DeepSeek R1 is
removed, a large reasoning distillation model can fill its role without code changes.

---

## Behavior

- **Model on disk → capabilities registered.** Model removed → capabilities disappear.
  No `None` values ever enter `CAPABILITY_MAP`.
- **Vision caps skipped if no mmproj.** A vision-capable model without a paired projection
  file registers only its text caps.
- **First match wins.** If two models match the same rule pattern (e.g., two DeepSeek
  variants), the one returned first by `scan_models()` (sorted alphabetically by name)
  wins. Later downloads don't silently override.
- **Startup log.** On every launch: `[Roamin] Capabilities: analysis, chat, code, ...`

---

## Impact

| File | Change |
|------|--------|
| `agent/core/llama_backend.py` | Lines 26–137 replaced with `_MODEL_FAMILY_RULES` + `_build_capability_map()` |
| `agent/core/agent_loop.py` | Line 243–248: replace `QWEN3_VL_8B_MMPROJ` import with `CAPABILITY_MAP` + `_MMPROJ_MAP` check |
| `tests/test_vision_model.py` | Remove named path imports; make assertions model-agnostic |
| `agent/core/model_scanner.py` | No changes — consumed as-is |
| `agent/core/model_router.py` | No changes — already imports `CAPABILITY_MAP` |

---

## Non-Goals

- **Automatic capability assignment for unknown models.** If a model doesn't match any
  rule pattern, it is ignored. The user adds a rule entry to opt a new model family in.
- **Hot reload.** `_build_capability_map()` runs once at import time. Restart Roamin to
  pick up new downloads.
- **Multi-model per capability.** One model per capability. No load-balancing or fallback
  chains within a capability.
