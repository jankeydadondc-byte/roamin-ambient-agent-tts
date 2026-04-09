## Why

Roamin currently depends on LM Studio and Ollama being actively running to discover and serve models, but those programs use auth tokens, custom APIs, and must be manually started — making Roamin fragile as a standalone agent. Every GGUF model on the system is already a self-contained file that llama-cpp-python can load directly; Roamin should find and use them without any intermediary.

## What Changes

- **Remove API-based discovery**: Replace `_discover_lmstudio()` and `_discover_ollama()` HTTP calls in `model_sync.py` with a single filesystem scanner
- **System-wide GGUF scan**: Walk all drive roots (depth-pruned, system dirs excluded) and any folder named `models`, collecting `.gguf` files
- **Ollama manifest resolver**: Read `~/.ollama/models/manifests/` to resolve SHA256 blob filenames to friendly `name:tag` model identifiers; only register blobs identified as the actual model weights layer (`application/vnd.ollama.image.model`)
- **File path stored in config**: Each discovered model entry stores its absolute `file_path` so `LlamaCppBackend` can load it directly — no server required
- **Router updated to load by path**: `model_router.py` passes `file_path` to `LlamaCppBackend` for `provider=llama_cpp` entries, enabling any discovered model to be used
- **`model_scan_dirs` in config**: `model_config.json` gains a `model_scan_dirs` array for user-configurable extra scan roots

## Capabilities

### New Capabilities

- `filesystem-model-scan`: Walk the local filesystem (all drives, depth-pruned) to find `.gguf` model files and return structured discovery results including friendly name and absolute path
- `ollama-manifest-resolve`: Parse Ollama's manifest directory to map SHA256 blob files to human-readable `name:tag` identifiers and identify which blob is the actual GGUF weights

### Modified Capabilities

- `model-config-sync`: Discovery source changes from HTTP provider APIs to filesystem scan + Ollama manifest resolver; discovered entries now include a `file_path` field; idempotent upsert logic and atomic write behavior are unchanged

## Impact

- `agent/core/model_sync.py` — primary rewrite of discovery layer; retains upsert/atomic write logic
- `agent/core/model_router.py` — pass `file_path` from config entry to `LlamaCppBackend` when `provider=llama_cpp`
- `agent/core/model_config.json` — add `model_scan_dirs` key; existing `llama_cpp` entries gain `file_path` field; LM Studio and Ollama entries converted to `provider=llama_cpp` with paths
- No changes to `LlamaCppBackend` itself — it already accepts a `Path` argument
- LM Studio and Ollama no longer need to be running for Roamin to use any model
