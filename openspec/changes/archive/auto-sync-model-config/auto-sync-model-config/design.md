## Context

`model_config.json` is the single source of truth for Roamin's capability-based model router (introduced in commit bbb914a). It is currently hand-maintained: new models loaded into LM Studio or pulled into Ollama are invisible to the router until a developer edits the file. There are two providers in play — LM Studio (OpenAI-compatible REST at `http://127.0.0.1:1234`) and Ollama (its own REST at `http://127.0.0.1:11434`) — plus one always-available local GGUF loaded via `llama_backend.py`. The existing `ModelRouter` only reads the config; it never writes it.

## Goals / Non-Goals

**Goals:**

- Auto-discover models from LM Studio and Ollama at startup
- Append net-new models to `model_config.json` with inferred capabilities
- Never overwrite or corrupt existing hand-crafted entries
- Never write to disk if nothing changed (idempotent)
- Survive provider unavailability gracefully (no crash)

**Non-Goals:**

- Removing stale entries (models that were once loaded but no longer are)
- Editing or improving capabilities on existing entries
- Syncing on a timer or background thread (startup-only for now)
- UI or API to trigger manual sync

## Decisions

### D1: New module `model_sync.py` rather than extending `model_router.py`

`ModelRouter` is a read-only router by design. Adding write responsibilities muddies the abstraction. A dedicated `model_sync.py` owns the discover→infer→write pipeline and can be tested independently.

*Alternative considered*: A `sync_from_providers()` method on `ModelRouter`. Rejected because it conflates routing (read) with config management (write), making mocking harder in tests.

---

### D2: Match by `model_id` field, not by `id` (slug)

`model_id` is the actual string sent to the provider API. Two entries could in theory have different slugs but the same model file. Matching on `model_id` avoids duplicate entries for the same underlying model. The comparison is case-insensitive and strips leading/trailing whitespace.

---

### D3: Heuristic capability inference via name substring rules

A lookup table of `{substring → [capabilities]}` rules, applied in order, with a default fallback. Rules are defined in `model_sync.py` as a module-level constant so they can be updated without touching logic. No ML, no LLM call.

*Alternative considered*: Call the model itself with a capability-probe prompt. Rejected — too slow, requires a loaded model, and circular (need capabilities to load the model).

---

### D4: Atomic write via temp file + `os.replace()`

Write to `model_config.json.tmp` in the same directory, then `os.replace()` (atomic on POSIX; best-effort on Windows). This ensures the file is never partially written.

---

### D5: `always_available = False` for all auto-inferred entries

Newly discovered LM Studio models may not be loaded at any given moment. Defaulting `always_available: false` is the conservative, correct default. The llama.cpp GGUF (already in config with `true`) is never touched.

---

### D6: Startup hook in `run_wake_listener.py`

The sync call goes in `run_wake_listener.py` before the `AgentLoop` or `ModelRouter` is constructed. No changes to `model_router.py` initialization needed — it reads the (now updated) file at construction time as before.

## Risks / Trade-offs

- **Race condition on first boot**: If `model_sync.py` runs before LM Studio has fully started, it discovers zero models. Mitigation: `always_available: false` means the router won't try to use them anyway; the missing models appear on next restart.
- **Heuristic misclassification**: A model named "deepseek-coder-r1" matches both `coder` and `r1` rules — it gets both capability sets merged, which is correct. A model with a generic name gets only the default set, which is safe (just less useful). Humans can still hand-edit afterward without the sync overwriting their work.
- **Windows atomic write**: `os.replace()` is atomic on NTFS when source and dest are on the same volume (they are). Risk is negligible.
- **Config grows over time**: Every newly seen model is appended. Stale entries are never removed. Over months the file will grow. Acceptable for now; a separate cleanup command is out of scope.

## Migration Plan

1. Deploy `model_sync.py` (new file, no breaking changes).
2. Add sync call to `run_wake_listener.py` startup sequence.
3. On next Roamin restart, any LM Studio/Ollama models not in config are auto-appended.
4. **Rollback**: Delete `model_sync.py`, remove the startup call. `model_config.json` changes are additive-only so no rollback of the data file is required.

## Open Questions

- Should the sync run with a short timeout (e.g. 2s per provider) or use the existing HTTP retry logic in `model_router.py`? → Recommend a simple 2s timeout, no retries (startup path should be fast).
- Should Qwen3 Coder 30B (Ollama) get `"planning"` added if it's discovered as a net-new entry? → No: per the prior design decision (commit bbb914a), it's HTTP-only and may be offline, so planning stays on the always-available GGUF.
