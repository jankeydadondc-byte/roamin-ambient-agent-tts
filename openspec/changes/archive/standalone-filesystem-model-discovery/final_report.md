# Archive: standalone-filesystem-model-discovery

**Status: ✅ COMPLETE (2026-04-04)**

## Summary

Full rewrite of `model_sync.py`. Replaced endpoint-based LM Studio/Ollama polling with: filesystem drive walk + `~/.lmstudio/models` scan for `.gguf` files; Ollama manifest blob resolution (`sha256-*` → `name:tag`); mmproj sibling detection. `model_router.py` updated to dispatch via `file_path` from config. 13 tests passing. 6 models auto-registered on first run; idempotent on restart.

## Acceptance checklist

- [x] `_build_ollama_manifest_map()` — walk `~/.ollama/models/manifests/`, parse JSON, extract digest→name:tag
- [x] `_discover_ollama_blobs()` — resolve blobs to friendly names
- [x] `_scan_dir_for_ggufs()` + `_find_mmproj()` — filesystem scanner
- [x] `_drive_walk()` — Windows drive letter walk, max_depth=5, skip-list
- [x] `_discover_filesystem()` — unified discovery with mmproj pairing
- [x] `sync_from_providers()` rewritten to call `_discover_filesystem()`
- [x] `model_router.py` — dispatch by `file_path` when present
- [x] `model_config.json` — `model_scan_dirs` key + `file_path` on existing entries
- [x] `tests/test_model_sync.py` — 13/13 passing
- [x] Manual: 6 models added on first run; 0 on second (idempotent)
- [x] Ollama `qwen3:8b` resolved correctly from blob

## Key files

- `agent/core/model_sync.py`
- `agent/core/model_router.py`
- `agent/core/model_config.json`
- `tests/test_model_sync.py`
