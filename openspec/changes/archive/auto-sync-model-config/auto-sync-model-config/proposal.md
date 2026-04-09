## Why

`model_config.json` is manually maintained, meaning newly loaded models in LM Studio or Ollama are silently invisible to Roamin's router — the agent can't use them until a developer hand-edits the config. With the capability-based routing system now in place (commit bbb914a), the config is the single source of truth for what the router can do; keeping it stale defeats that investment.

## What Changes

- **Model discovery at startup**: On each Roamin startup, query all reachable provider endpoints (LM Studio `/v1/models`, Ollama `/api/tags`, llama.cpp always-available) and collect their reported model IDs.
- **Idempotent upsert into model_config.json**: For each discovered model, check if it is already registered by `model_id`. If yes — skip it entirely (no overwrites). If no — infer a sensible config entry and append it.
- **Capability inference**: Newly discovered models get capabilities inferred from their name/size (heuristic rules). Human-assigned capabilities on existing entries are never touched.
- **First-run backfill**: On the very first run, backfill any LM Studio or Ollama models not yet in the config, so the existing hand-crafted entries are preserved and gaps are filled.

## Capabilities

### New Capabilities

- `model-discovery`: Query each configured provider endpoint and return the list of model IDs currently available on that provider.
- `model-config-sync`: Compare discovered models against `model_config.json`, produce a list of net-new models, infer their config entries, and write them to the file idempotently.

### Modified Capabilities

<!-- None — no existing spec-level behavior is changing. -->

## Impact

- `agent/core/model_router.py` — gains a `sync_from_providers()` method (or thin wrapper calling the new sync module).
- `agent/core/model_config.json` — data file modified at runtime; must remain valid JSON at all times (atomic write).
- New module `agent/core/model_sync.py` — owns discovery + upsert logic, keeping `model_router.py` focused on routing.
- `run_wake_listener.py` (or equivalent startup entry point) — calls sync once at boot before the router is first used.
- No breaking changes to existing routing rules or capability assignments.
