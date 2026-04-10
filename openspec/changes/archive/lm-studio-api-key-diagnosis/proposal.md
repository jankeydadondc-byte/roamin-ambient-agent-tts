# Proposal: Diagnose & Fix LM Studio API Key Integration

## Problem Statement

User set `LM_API_TOKEN=sk-lm-VFHtSkqr:wqsqkc3RSk1LP25OLTiv` as a **Windows User-level environment variable**, but LM Studio API calls from Roamin don't authenticate. The key "doesn't work."

## Root Cause Analysis

After investigating the full codebase, I found **three independent issues** that combine to make the API key invisible:

### Issue 1: model_router.py never sends auth headers (PRIMARY)

`agent/core/model_router.py` lines 163-222 build HTTP requests to LM Studio with **zero auth headers**:

```python
response = requests.post(url, json=payload, timeout=5)
```

No `Authorization: Bearer <token>` header is ever attached. Even if the environment variable is perfectly set, the code never reads it or uses it.

### Issue 2: secrets.py doesn't know about LM_API_TOKEN

`agent/core/secrets.py` loads secrets at startup, and `run_wake_listener.py` calls:

```python
check_secrets(optional=["ROAMIN_CONTROL_API_KEY", "ROAMIN_DEBUG"])
```

`LM_API_TOKEN` is not in the optional or required list. It won't be loaded from `.env` (though it IS available via `os.environ` since the user set it at the Windows level).

### Issue 3: No .env file exists

There's no `.env` file at the project root. Only `.env.example` exists. The secrets loader logs:

```
No .env file at C:\AI\roamin-ambient-agent-tts\.env — using environment variables only
```

This isn't fatal (env vars still work), but it means the user can't use `.env` as an alternative source.

## Why It Fails End-to-End

```
User sets LM_API_TOKEN in Windows Environment Variables
    ↓
os.environ["LM_API_TOKEN"] = "sk-lm-VFHtSkqr:..."  ← present at runtime
    ↓
model_router.py sends POST to http://127.0.0.1:1234/v1/chat/completions
    ↓
No Authorization header attached  ← THE GAP
    ↓
LM Studio (if auth enabled) rejects with 401 or drops connection
```

## Solution

### Fix 1: Wire Bearer token into HTTP fallback requests (model_router.py)

When sending requests to LM Studio (or any HTTP endpoint), check for an API key and attach it as a Bearer token:

```python
headers = {"Content-Type": "application/json"}
api_key = os.environ.get("LM_API_TOKEN") or os.environ.get("ROAMIN_LM_STUDIO_KEY")
if api_key:
    headers["Authorization"] = f"Bearer {api_key}"

response = requests.post(url, json=payload, headers=headers, timeout=5)
```

### Fix 2: Register LM_API_TOKEN in the secrets system

Add `LM_API_TOKEN` to the optional secrets check in `run_wake_listener.py`:

```python
check_secrets(optional=["ROAMIN_CONTROL_API_KEY", "ROAMIN_DEBUG", "LM_API_TOKEN"])
```

### Fix 3: Support per-model API keys in model_config.json (optional)

Allow `api_key_env` field per model entry so different endpoints can use different keys:

```json
{
  "id": "deepseek-r1-8b-lmstudio",
  "endpoint": "http://127.0.0.1:1234",
  "api_key_env": "LM_API_TOKEN"
}
```

This is optional but future-proofs for multi-provider setups.

## Verification

After fix, with LM Studio running and auth enabled:

1. `curl -H "Authorization: Bearer sk-lm-..." http://127.0.0.1:1234/v1/models` should return model list
2. Roamin voice query routed to LM Studio should get a valid response (not timeout/401)
3. Logs should show: `[Roamin] LM Studio auth: Bearer token attached`

## Risk Assessment

**Risk Level:** Low
- Only adds an optional header to existing HTTP requests
- No auth header = same behavior as before (backward compatible)
- No security risk (token only sent to localhost endpoints)
