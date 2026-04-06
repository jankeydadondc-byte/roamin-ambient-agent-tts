# Archive: auto-sync-model-config

**Status: ✅ COMPLETE — superseded by standalone-filesystem-model-discovery**

## Summary

Initial auto-sync proposal: `model_sync.py` with LM Studio + Ollama endpoint polling at startup. Implemented and tested. Subsequently superseded by the broader `standalone-filesystem-model-discovery` rewrite which replaced endpoint polling with full filesystem scanning and Ollama manifest blob resolution.

## Acceptance checklist

- [x] `model_sync.py` created with `sync_from_providers()`
- [x] `_infer_capabilities()` heuristics
- [x] `_discover_lmstudio()` + `_discover_ollama()` endpoint discovery
- [x] Atomic config write via temp file + `os.replace()`
- [x] Idempotency: second run adds 0 entries
- [x] Wired into `run_wake_listener.py` startup
- [x] `tests/test_model_sync.py` passing
- [~] Manual smoke tests — confirmed working at startup (6 models added on first run)

## Note

`_discover_lmstudio` and `_discover_ollama` functions were later deleted as part of `standalone-filesystem-model-discovery` which replaced endpoint-based discovery with filesystem walk + Ollama manifest blob resolution.
