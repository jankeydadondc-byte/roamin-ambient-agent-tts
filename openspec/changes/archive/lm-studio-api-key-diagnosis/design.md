# Design: LM Studio API Key Integration

## Current Architecture (Broken)

```
[User sets LM_API_TOKEN in Windows]
    ↓
[os.environ has it at runtime]
    ↓
[model_router.py builds HTTP request]
    ↓
[requests.post(url, json=payload, timeout=5)]  ← NO AUTH HEADER
    ↓
[LM Studio rejects or ignores]
```

## Target Architecture (Fixed)

```
[User sets LM_API_TOKEN in Windows OR .env]
    ↓
[secrets.py loads at startup, logged as optional]
    ↓
[model_router.py reads API key from env or model_config.json]
    ↓
[requests.post(url, json=payload, headers={"Authorization": "Bearer <key>"}, timeout=5)]
    ↓
[LM Studio authenticates and responds]
```

## Implementation Details

### Change 1: model_router.py — attach Bearer token to HTTP requests

**File:** `agent/core/model_router.py`
**Location:** Lines 163-194 (HTTP fallback section)

**Before:**
```python
response = requests.post(url, json=payload, timeout=5)
```

**After:**
```python
# Build headers — attach Bearer token if available for this endpoint
headers = self._auth_headers(task)
response = requests.post(url, json=payload, headers=headers, timeout=5)
```

New helper method on `ModelRouter`:

```python
def _auth_headers(self, task: str) -> dict[str, str]:
    """Build HTTP headers for a task's endpoint, including auth if configured."""
    headers: dict[str, str] = {"Content-Type": "application/json"}

    # Check per-model api_key_env in model_config.json
    cfg = self._config_for_task(task)
    if cfg:
        env_var = cfg.get("api_key_env")
        if env_var:
            key = os.environ.get(env_var)
            if key:
                headers["Authorization"] = f"Bearer {key}"
                return headers

    # Fallback: global LM_API_TOKEN (covers LM Studio default)
    global_key = os.environ.get("LM_API_TOKEN")
    if global_key:
        headers["Authorization"] = f"Bearer {global_key}"

    return headers
```

### Change 2: run_wake_listener.py — register LM_API_TOKEN as optional secret

**File:** `run_wake_listener.py`
**Location:** Line ~255

**Before:**
```python
check_secrets(optional=["ROAMIN_CONTROL_API_KEY", "ROAMIN_DEBUG"])
```

**After:**
```python
check_secrets(optional=["ROAMIN_CONTROL_API_KEY", "ROAMIN_DEBUG", "LM_API_TOKEN"])
```

### Change 3: model_config.json — add api_key_env to LM Studio entries

**File:** `agent/core/model_config.json`

Add optional `api_key_env` field to any model that needs auth:

```json
{
  "id": "deepseek-r1-8b-lmstudio",
  "name": "DeepSeek R1 Qwen3 8B",
  "provider": "lmstudio",
  "model_id": "DeepSeek-R1-0528-Qwen3-8B-Q4_K_M.gguf",
  "endpoint": "http://127.0.0.1:1234",
  "api_key_env": "LM_API_TOKEN",
  "capabilities": ["reasoning", "analysis", "deep_thinking"]
}
```

This is optional — if omitted, the global `LM_API_TOKEN` fallback applies.

### Change 4: .env.example — document LM_API_TOKEN

**File:** `.env.example`

Add:
```
# LM Studio API token (for authenticated LM Studio endpoints)
# Get from: LM Studio Settings -> Developer -> Core -> Authentication
# LM_API_TOKEN=sk-lm-your-token-here
```

## How _auth_headers resolves the key

Priority order:
1. Per-model `api_key_env` in model_config.json → reads that env var
2. Global `LM_API_TOKEN` env var → fallback for any endpoint
3. No key → no Authorization header (backward compatible)

## Testing Plan

### Unit test: _auth_headers returns correct headers

```python
def test_auth_headers_with_lm_api_token(monkeypatch):
    monkeypatch.setenv("LM_API_TOKEN", "sk-test-123")
    router = ModelRouter()
    headers = router._auth_headers("default")
    assert headers.get("Authorization") == "Bearer sk-test-123"

def test_auth_headers_no_token():
    router = ModelRouter()
    headers = router._auth_headers("default")
    assert "Authorization" not in headers
```

### Integration test: LM Studio accepts authenticated request

```bash
# With LM Studio running + auth enabled:
curl -H "Authorization: Bearer sk-lm-VFHtSkqr:wqsqkc3RSk1LP25OLTiv" \
     http://127.0.0.1:1234/v1/models
# Should return model list (not 401)
```

### Voice test: Roamin → LM Studio route works

```
User: "use deepseek to explain what a hash map is"
Expected: Routes to LM Studio → auth header attached → valid response spoken
```
