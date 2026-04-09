## 1. Create model_sync.py

- [x] 1.1 Create `agent/core/model_sync.py` with module docstring and imports (`json`, `logging`, `os`, `pathlib`, `requests`)
- [x] 1.2 Define `CAPABILITY_HEURISTICS` constant — ordered list of `(substring, [capabilities])` tuples covering: `r1`/`deepseek-r1`, `coder`, `vision`/`-vl-`, `reasoning`, `instruct`, and catch-all default `["fast", "general", "chat"]`
- [x] 1.3 Implement `_infer_capabilities(model_id: str) -> list[str]` — applies heuristics in order, merges matched capability lists, returns default if no match
- [x] 1.4 Implement `_discover_lmstudio(endpoint: str, timeout: float = 2.0) -> list[str]` — GET `/v1/models`, return list of model IDs, catch all exceptions and return `[]` with a warning log
- [x] 1.5 Implement `_discover_ollama(endpoint: str, timeout: float = 2.0) -> list[str]` — GET `/api/tags`, return list of model names, catch all exceptions and return `[]` with a warning log
- [x] 1.6 Implement `_build_entry(provider: str, endpoint: str, model_id: str) -> dict` — returns a full model config entry dict with inferred `id` slug, `capabilities`, `always_available: false`, and `requires_manual_load` omitted
- [x] 1.7 Implement `sync_from_providers(config_path: Path | None = None) -> int` — loads config, collects all existing `model_id` values (case-insensitive set), runs discovery on all providers found in config's unique endpoints, appends net-new entries, writes atomically via temp file + `os.replace()`, returns count of entries added

## 2. Wire Into Startup

- [x] 2.1 In `run_wake_listener.py`, import `model_sync` and call `model_sync.sync_from_providers()` inside a `try/except Exception` block before `ModelRouter` or `AgentLoop` is instantiated
- [x] 2.2 Log the return value: `"model_sync: %d new model(s) added to config"` at INFO level

## 3. Tests

- [x] 3.1 In `tests/test_model_sync.py`, write a test for `_infer_capabilities` covering: `r1` name → includes `reasoning`, `coder` name → includes `code`, unknown name → returns default set
- [x] 3.2 Write a test for `sync_from_providers` with a tmp config — mock `_discover_lmstudio` and `_discover_ollama` to return one new model each; assert both are appended and original entries are untouched
- [x] 3.3 Write a test for idempotency — run `sync_from_providers` twice with the same discovered models; assert the second run adds 0 entries and does not write to disk
- [x] 3.4 Write a test for provider unavailability — mock both discovery functions to raise `requests.ConnectionError`; assert `sync_from_providers` returns 0 and does not raise

## 4. Verify

- [x] 4.1 Run `python -m pytest tests/test_model_sync.py -v` — all tests pass
- [x] 4.2 Start Roamin and check startup log for `"model_sync: N new model(s) added"` line (fixed: changed logger.info → print() so line is visible in terminal/log)
- [x] 4.3 Open `agent/core/model_config.json` and confirm any LM Studio/Ollama models not previously listed are now present with correct provider/endpoint/capabilities fields (24 models total, 18 auto-added)
- [x] 4.4 Restart Roamin a second time and confirm no duplicate entries appear and the log shows `"0 new model(s) added"` (verified: count stayed at 24 after restart)
