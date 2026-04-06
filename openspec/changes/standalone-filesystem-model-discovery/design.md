## Context

Roamin's `model_sync.py` currently discovers models by querying LM Studio's `/v1/models` REST endpoint and Ollama's `/api/tags` endpoint at startup. This has three failure modes: (1) LM Studio requires a per-installation bearer token with no stable auto-discovery path, (2) Ollama must be running, and (3) neither program needs to be installed at all for llama-cpp-python to load GGUFs directly. The `LlamaCppBackend` already loads models by `Path` — the router just needs to know what paths exist and how to name them.

Ollama complicates things further: its `~/.ollama/models/blobs/` directory stores GGUF files under opaque `sha256-<hash>` names. However Ollama also writes human-readable **manifests** at `~/.ollama/models/manifests/registry.ollama.ai/library/<name>/<tag>` — each manifest JSON contains a `layers` array where the layer with `mediaType: "application/vnd.ollama.image.model"` records the `digest` (SHA256) of the real weights file. This gives a complete `sha256 → name:tag` lookup table without any server dependency.

## Goals / Non-Goals

**Goals:**

- Discover all `.gguf` files on the system without requiring any external server
- Resolve Ollama SHA256 blob filenames to friendly `name:tag` identifiers via manifest parsing
- Store `file_path` on each config entry so the router can pass it directly to `LlamaCppBackend`
- Keep the idempotent upsert and atomic write behaviour from the existing `model_sync.py`
- Expose `model_scan_dirs` in `model_config.json` for user-configurable extra roots

**Non-Goals:**

- Loading all discovered models at startup (one-at-a-time VRAM swap is unchanged)
- Removing stale entries from config
- Discovering models in non-GGUF formats (ONNX, safetensors, etc.)
- Scanning network drives or UNC paths
- GPU size/VRAM fitness check at discovery time

## Decisions

### D1: Single `_discover_filesystem()` replaces both HTTP discovery functions

A flat function that returns `list[dict]` of `{model_id, file_path, provider}` records covers all sources uniformly. Caller logic (deduplication, build_entry) is unchanged. The HTTP functions are deleted entirely — no feature flag needed since LM Studio/Ollama provider entries in config already have `file_path` after the first sync.

### D2: Scan strategy — well-known dirs first, then depth-limited drive walk

**Well-known dirs** are scanned unconditionally and without depth limit:

- `~/.lmstudio/models/`
- `~/.ollama/models/blobs/` (resolved via manifests)
- `C:\AI\` (project workspace root)
- Any paths listed in `model_scan_dirs` in config

**Drive walk** iterates `Path(d + ":\\")` for each available drive letter, descending into directories named `models` (case-insensitive) up to depth 5. Anything found in a well-known dir is not re-added by the drive walk (dedup by absolute path).

*Alternative considered*: Full recursive scan of all drives. Rejected — too slow on large drives (100GB+ `node_modules` trees, game install dirs). The drive walk only descends when it finds a directory named `models`, making it fast in practice.

### D3: Ollama manifest resolution builds a `{sha256_hex: name_tag}` map before scanning blobs

Walk all files under `~/.ollama/models/manifests/` recursively. Each file is a JSON manifest. Parse `layers` for the entry with `mediaType == "application/vnd.ollama.image.model"` and extract the `digest` field (`sha256:<hex>`). The filename path encodes the model name: `.../library/<name>/<tag>`. Build the full map first, then map each blob file to its friendly name when scanning `blobs/`.

Blobs with no manifest entry are skipped — they are config/template/system-prompt blobs, not model weights.

### D4: `file_path` stored as a string in `model_config.json`

Paths are OS-specific strings. Stored under key `"file_path"` alongside `model_id`, `provider`, `endpoint`. When the router dispatches to `llama_cpp`, it checks for `file_path` first; if present it passes it to `LlamaCppBackend(model_path=Path(entry["file_path"]))`. Existing entries without `file_path` continue to use `CAPABILITY_MAP` as today.

### D5: `provider` set to `llama_cpp` for all filesystem-discovered entries

The router's primary dispatch path already checks `CAPABILITY_MAP` for `llama_cpp` entries. To make a newly discovered model routable, we need it reachable via that path. Storing `provider=llama_cpp` + `file_path` is sufficient — the router gains a secondary lookup: if `file_path` is set on the selected model, construct a `LlamaCppBackend` from it directly, bypassing `CAPABILITY_MAP`.

### D6: `model_scan_dirs` defaults in code, overridden by config

Default scan roots are defined as a module-level constant in `model_sync.py`. If `model_config.json` contains `"model_scan_dirs": [...]`, those are appended (not replaced) so well-known paths are always included.

### D7: mmproj pairing — heuristic filename match

When a `.gguf` file is discovered, scan the same directory for a sibling file matching `*mmproj*`. If found, store it under `"mmproj_path"` in the config entry. The router passes it to `LlamaCppBackend(mmproj_path=...)` if present.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Scan takes 5–10s on large drives | Well-known dirs checked first; drive walk only descends into `models`-named dirs. Startup delay is one-time per session. |
| Exotic Ollama quant fails to load in llama-cpp-python | Caught at `LlamaCppBackend.load()` time, not discovery time. Router gracefully falls back to next model. |
| Large model (80B) auto-added and accidentally selected | `always_available: false` — router only selects it if explicitly routed. No surprise VRAM exhaustion. |
| Config grows unboundedly | Same as today; deliberate non-goal. Cleanup is a separate future command. |
| `os.scandir` raises `PermissionError` on restricted dirs | Caught per-directory; scan continues. |
| Two `.gguf` files with the same slug after `_slugify()` | Second one gets `_2` suffix appended to `id` (not `model_id`); both are registered. |

## Migration Plan

1. Replace `model_sync.py` discovery functions with filesystem scanner + Ollama resolver.
2. Add `file_path` field handling to `model_router.py` dispatch.
3. Add `model_scan_dirs` to `model_config.json`; backfill `file_path` on existing `llama_cpp` entries.
4. On next Roamin restart, all local GGUFs are discovered and appended.
5. **Rollback**: Revert `model_sync.py` and `model_router.py`. Config additions are additive-only — no rollback of `model_config.json` required. Existing entries are never modified.

## Open Questions

- Should the drive walk also check dirs named `gguf` or `llm` in addition to `models`? → Start with `models` only; add others based on real-world feedback.
- Should mmproj pairing be fuzzy (e.g. same base name prefix) or strict (sibling `*mmproj*` glob)? → Sibling glob is safe and covers all known naming conventions (LM Studio, Hugging Face).
