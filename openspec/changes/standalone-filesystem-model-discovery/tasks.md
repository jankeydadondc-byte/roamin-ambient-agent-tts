## 1. Ollama Manifest Resolver

- [x] 1.1 In `agent/core/model_sync.py`, add `_build_ollama_manifest_map() -> dict[str, str]` — walk `~/.ollama/models/manifests/` recursively; for each file, parse JSON, find the layer with `mediaType == "application/vnd.ollama.image.model"`, extract `digest` (`sha256:<hex>`), derive `name:tag` from the file path (`.../library/<name>/<tag>`); skip malformed files with a warning log; return empty dict if manifests dir absent
- [x] 1.2 Add `_discover_ollama_blobs() -> list[dict]` — call `_build_ollama_manifest_map()`, scan `~/.ollama/models/blobs/`, for each file named `sha256-<hex>` look up the hex in the map; if found emit `{model_id: name:tag, file_path: str(path), provider: "llama_cpp"}`; skip files with no map entry; return empty list if blobs dir absent

## 2. Filesystem Scanner

- [x] 2.1 Add module-level constant `_WELL_KNOWN_SCAN_DIRS: list[Path]` — `Path.home() / ".lmstudio" / "models"` and `Path("C:/AI")`; skip entries that don't exist
- [x] 2.2 Add `_SCAN_DIR_SKIP: frozenset[str]` — lower-cased names: `windows`, `program files`, `program files (x86)`, `programdata`, `$recycle.bin`, `system volume information`, `recovery`, `node_modules`, `.git`, `__pycache__`, `site-packages`
- [x] 2.3 Add `_scan_dir_for_ggufs(directory: Path) -> list[Path]` — `os.scandir()` the dir, catching `PermissionError` silently; collect `.gguf` files whose name does not contain `mmproj`; return list of absolute Paths
- [x] 2.4 Add `_find_mmproj(gguf_path: Path) -> Path | None` — glob `gguf_path.parent` for `*mmproj*` (case-insensitive); return first match or `None`
- [x] 2.5 Add `_drive_walk(extra_dirs: list[Path], max_depth: int = 5) -> list[Path]` — iterate all available Windows drive letters; for each drive, recurse directories named `models` (case-insensitive) up to `max_depth`; skip any dir whose name (lowercased) is in `_SCAN_DIR_SKIP`; collect `.gguf` files via `_scan_dir_for_ggufs`; skip paths already in `seen` set; return deduplicated list
- [x] 2.6 Add `_discover_filesystem(config: dict) -> list[dict]` — collect extra dirs from `config.get("model_scan_dirs", [])`, build union of well-known dirs + extra + drive walk results (deduped by absolute path), call `_find_mmproj` for each, emit records `{model_id: filename_stem, file_path: str, provider: "llama_cpp", mmproj_path: str|None}`; merge Ollama blob records from `_discover_ollama_blobs()`

## 3. Rewrite sync_from_providers

- [x] 3.1 Replace the existing `seen_endpoints` loop in `sync_from_providers()` with a call to `_discover_filesystem(config)` — all other logic (existing_ids dedup set, `_build_entry`, atomic write, return count) remains unchanged
- [x] 3.2 Update `_build_entry()` to accept and pass through `file_path: str | None` and `mmproj_path: str | None` — include them in the returned dict when not None
- [x] 3.3 Update `existing_ids` dedup logic: check `file_path` values of existing entries (in addition to `model_id`) so re-runs don't re-add the same file under a different slug
- [x] 3.4 Delete `_discover_lmstudio`, `_discover_ollama`, `_read_lmstudio_key`, and `_LMSTUDIO_KEY_PATH` — they are no longer used

## 4. Router: load by file_path

- [x] 4.1 In `agent/core/model_router.py` `respond()`, after the `CAPABILITY_MAP` lookup succeeds, check if the selected config entry has a `file_path` key; if yes, construct `LlamaCppBackend(model_path=Path(entry["file_path"]), mmproj_path=Path(entry["mmproj_path"]) if entry.get("mmproj_path") else None)` instead of using the CAPABILITY_MAP path object
- [x] 4.2 If `file_path` is absent (legacy entry), fall through to existing CAPABILITY_MAP dispatch as today — no regression for existing hardcoded models

## 5. Update model_config.json

- [x] 5.1 Add `"model_scan_dirs": []` key to `model_config.json` (empty array — populated by user if needed)
- [x] 5.2 Add `"file_path"` to all existing `provider=llama_cpp` entries using known absolute paths from `llama_backend.py` constants

## 6. Tests

- [x] 6.1 In `tests/test_model_sync.py`, add a test for `_build_ollama_manifest_map` — create a temp manifests dir tree with two manifests (one valid, one malformed JSON); assert valid one is in the map, malformed is skipped without raising
- [x] 6.2 Add a test for `_discover_ollama_blobs` — mock `_build_ollama_manifest_map` to return `{"abc123": "qwen3:8b"}`; create a temp blobs dir with `sha256-abc123` and `sha256-unknown`; assert only `qwen3:8b` is discovered
- [x] 6.3 Add a test for `_discover_filesystem` — create a temp dir tree with two `.gguf` files (one with mmproj sibling, one without) and one `mmproj`-named `.gguf`; assert two records returned, mmproj file excluded, mmproj_path populated on the correct entry
- [x] 6.4 Add a test for `sync_from_providers` dedup by `file_path` — config has an existing entry with `file_path`; mock `_discover_filesystem` to return the same path; assert 0 entries added and no disk write
- [x] 6.5 Run `python -m pytest tests/test_model_sync.py -v` — all tests pass (13/13)

## 7. Verify

- [x] 7.1 Run `python -c "from agent.core.model_sync import _discover_filesystem, sync_from_providers; import json; cfg = json.loads(open('agent/core/model_config.json').read()); print(_discover_filesystem(cfg))"` — output lists local GGUF files with friendly names
- [x] 7.2 Start Roamin and check startup log for `"model_sync: N new model(s) added to config"` with N > 0 on first run — confirmed: **6 new model(s) added to config** at 20:58
- [x] 7.3 Restart Roamin a second time — log shows `"0 new model(s) added"` confirming idempotency — confirmed at 21:02:54
- [x] 7.4 Verify Ollama blobs appear in config with `name:tag` model_id values (not SHA256 strings) — `qwen3:8b` resolved correctly, deduplicated against existing ollama entry
