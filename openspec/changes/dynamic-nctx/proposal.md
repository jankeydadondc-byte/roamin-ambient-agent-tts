# Dynamic Context Window Sizing (n_ctx)

**Date:** 2026-04-19
**Status:** TABLED — spec complete, not yet implemented

---

## Why

`llama_backend.py` currently assigns fixed n_ctx values per capability (32768 for chat/default,
16384 for code, 8192 for vision). These are worst-case ceilings — allocated at model load time
regardless of how large the actual request is. A one-sentence query consumes the same VRAM as
a 20,000-token document. This means:

- VRAM is over-committed on every short request
- Chatterbox TTS and the GGUF model compete for a shared pool that is inflated by empty KV cache slots
- n_ctx is hardcoded as a guess rather than derived from hardware reality

The goal: let the system measure what it has (VRAM), measure what the request needs (token count),
and allocate only the difference — automatically, without any hardcoded limits.

---

## What Changes

### Three Layered Mechanisms

**Layer 1 — VRAM-aware ceiling (hardware self-discovery)**

At model load time, query available VRAM and calculate the maximum safe n_ctx for the model
being loaded. This becomes the ceiling — never exceeded regardless of request size.

```
free_vram = torch.cuda.mem_get_info()[0]         # bytes free
kv_per_token = 2 × n_layers × n_heads × head_dim × dtype_bytes
vram_ceiling = int((free_vram × 0.75) / kv_per_token)
```

- `0.75` leaves 25% headroom for activations, logits, and Chatterbox VRAM fluctuations
- If VRAM changes between requests (Chatterbox starts/stops), the ceiling is recalculated
  on the next load
- Model families expose their architecture constants via `_MODEL_ARCH` (see below)

**Layer 2 — Pre-flight token counting (request self-sizing)**

Before dispatching to the model, tokenize the full prompt and compute the minimum n_ctx needed:

```python
input_tokens = len(backend._llm.tokenize(prompt.encode()))
needed_ctx = input_tokens + max_response_tokens + 256   # 256 = safety buffer
```

The model is loaded (or reloaded) with `min(needed_ctx, vram_ceiling)`. Short queries
allocate 2048. Long document pastes allocate 14336. Nothing over-allocated.

**Layer 3 — Reload-on-demand with hysteresis**

The `ModelRegistry` tracks the currently loaded n_ctx. On each request:

1. If loaded model matches capability AND loaded n_ctx ≥ needed_ctx → reuse, no reload
2. If needed_ctx > loaded n_ctx → unload and reload with new n_ctx
3. If needed_ctx has shrunk significantly (< 50% of loaded n_ctx) → still reuse (no shrink reload)
   - Avoids thrashing on alternating short/long requests

---

## New Data Structures

### `_MODEL_ARCH` — per-family architecture constants

Added alongside `_MODEL_FAMILY_RULES` in `llama_backend.py`:

```python
_MODEL_ARCH: dict[str, dict] = {
    r"deepseek.*r1": {"n_layers": 28, "n_heads": 16, "head_dim": 128, "dtype_bytes": 2},
    r"qwen.*\bvl\b": {"n_layers": 28, "n_heads": 16, "head_dim": 128, "dtype_bytes": 2},
    r"qwen.*coder":  {"n_layers": 48, "n_heads": 40, "head_dim": 128, "dtype_bytes": 2},
    r"ministral":    {"n_layers": 40, "n_heads": 32, "head_dim": 128, "dtype_bytes": 2},
}
# dtype_bytes: 2 = float16/bfloat16 (Q4_K_M quantized models use BF16 for KV cache by default)
```

Used only for ceiling calculation. If a model doesn't match any arch entry, ceiling defaults
to a conservative 8192.

### `ModelRegistry.get_backend()` signature change

```python
def get_backend(
    self,
    capability: str,
    messages: list[dict] | None = None,   # NEW: for pre-flight token counting
    max_response_tokens: int = 512,        # NEW: added to needed_ctx calculation
) -> LlamaCppBackend:
```

Backward compatible — existing callers without `messages` fall through to the VRAM ceiling only.

---

## Behavior Table

| Situation | Current | With Dynamic n_ctx |
|-----------|---------|-------------------|
| One-sentence query | 32768 allocated | ~2048 allocated |
| 5-turn conversation | 32768 allocated | ~4096 allocated |
| Long code paste (8K tokens) | 16384 allocated | ~9216 allocated |
| Chatterbox using 4GB VRAM | 32768 — may OOM | ceiling recalculates, fits |
| New GPU with 24GB VRAM | 32768 (capped) | ceiling scales up automatically |
| Short query after long query | 32768 (no reload) | reuse — hysteresis prevents shrink reload |

---

## Impact

| File | Change |
|------|--------|
| `agent/core/llama_backend.py` | Add `_MODEL_ARCH`, `_vram_ceiling()`, `_count_tokens()`. Modify `ModelRegistry.get_backend()` to accept messages + compute needed_ctx. Add hysteresis check. |
| `agent/core/voice/wake_listener.py` | Pass `messages` to `get_backend()` via `get_llm_response()` — requires threading through the call chain |
| `agent/core/agent_loop.py` | Same — pass messages through to get_backend |
| `tests/test_llama_backend.py` | Add tests for ceiling calculation and hysteresis logic |

---

## Non-Goals

- **Streaming resize** — n_ctx cannot change mid-generation. Sizing is locked at load time.
- **Multi-request batching** — one request at a time; n_ctx is per-request not per-batch.
- **CPU-only VRAM calculation** — if CUDA is unavailable, fall back to a fixed 8192 ceiling.
  CPU RAM is plentiful enough that this case doesn't need dynamic sizing.
- **Shrink reloading** — never reload just to save memory. Only reload when current n_ctx is
  insufficient for the next request.

---

## Implementation Order

1. Add `_MODEL_ARCH` constants and `_vram_ceiling(model_path)` function
2. Add `_count_tokens(backend, messages)` helper
3. Modify `ModelRegistry.get_backend()` — ceiling + hysteresis logic
4. Update `get_llm_response()` to accept and pass through `messages` for sizing
5. Thread `messages` through wake_listener → model_router → get_llm_response
6. Add unit tests for ceiling and hysteresis (mock torch.cuda.mem_get_info)

---

## Risk

**Medium.** The ceiling formula requires accurate `_MODEL_ARCH` values. Wrong values
(e.g. wrong n_layers) produce an incorrect ceiling — too high risks OOM, too low limits
usable context. Mitigation: validate arch constants against model card metadata before
publishing; default conservatively to 8192 if unknown.
