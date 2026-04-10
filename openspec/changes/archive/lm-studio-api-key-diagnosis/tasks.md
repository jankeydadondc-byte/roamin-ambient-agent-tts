# Tasks: LM Studio API Key Integration

## Implementation

- [ ] 1.1 — Add `_auth_headers(task)` method to `ModelRouter` in `agent/core/model_router.py`
  - Reads `api_key_env` from model config, falls back to `LM_API_TOKEN` env var
  - Returns dict with `Authorization: Bearer <key>` if key found
- [ ] 1.2 — Wire `_auth_headers()` into HTTP fallback requests in `model_router.py` (line ~194)
  - Both chat completions and raw generation paths
- [ ] 1.3 — Add `api_key_env: "LM_API_TOKEN"` to LM Studio entries in `model_config.json`
- [ ] 1.4 — Register `LM_API_TOKEN` as optional secret in `run_wake_listener.py`
- [ ] 1.5 — Add `LM_API_TOKEN` documentation to `.env.example`
- [ ] 1.6 — Add unit tests for `_auth_headers()` (with token, without token, per-model override)
- [ ] 1.7 — Manual test: start LM Studio with auth enabled, verify Roamin can connect

## Verification

- [ ] Restart Roamin after changes
- [ ] Startup log shows: `Optional secret 'LM_API_TOKEN' not set` OR loads successfully
- [ ] With LM Studio running + auth: voice query routed to LM Studio succeeds
- [ ] Without LM_API_TOKEN set: no auth header sent (backward compatible)
