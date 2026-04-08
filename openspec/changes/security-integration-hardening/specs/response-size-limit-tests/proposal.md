# Proposal: Response Size Limit Tests (Priority 7, Task 11)

## Context

`model_router.py` HTTP fallback path gained a 256KB response size guard in commit `2b99f96`:

```python
if len(response.content) > 256 * 1024:
    raise RuntimeError(
        f"Response too large ({len(response.content)} bytes, max 262144)"
    )
```

This guard runs during the retry loop inside `ModelRouter._http_fallback()`. It was
implemented but not tested. The OpenSpec tasks.md tracks it as task 11 (open).

## Why Tests Are Needed

The guard is a one-liner, but the *wiring* is what matters:

- Is the check in the right place (before `response.json()`, not after)?
- Does it raise the right exception type (`RuntimeError`, not `ValueError`)?
- Does the error message contain the actual byte count?
- Is it inside the retry loop, or does it bypass retries?
- Does a normal-size response still reach the caller correctly?

Without tests, a future refactor of the retry loop could silently remove or break the guard.

## What Changes

Add **3 tests** to `tests/test_model_router.py` covering the HTTP fallback size limit.

All three tests mock `requests.post` (via `unittest.mock.patch`) to return a fabricated
response object — no real network calls, no real model endpoint needed.

### Test 1: Normal response passes through (chat format)

Mock a response with `content` under 256KB. Verify:
- No exception raised
- Return value equals the `choices[0].message.content` string from the mock JSON

### Test 2: Normal response passes through (raw/Ollama format)

Same as Test 1 but using the `response` key (Ollama-style endpoint). Confirms the size
guard doesn't interfere with the raw format path.

### Test 3: Oversized response raises RuntimeError

Mock a response with `content` exactly `256 * 1024 + 1` bytes (one byte over). Verify:
- `RuntimeError` is raised
- Error message contains the byte count
- Error message contains `"max 262144"` (so the limit is visible in logs)

## Implementation Notes

**Mock target:** `requests.post` in `agent.core.model_router`

```python
from unittest.mock import MagicMock, patch

mock_resp = MagicMock()
mock_resp.content = b"x" * (256 * 1024 + 1)   # oversized
mock_resp.raise_for_status.return_value = None
with patch("agent.core.model_router.requests.post", return_value=mock_resp):
    ...
```

For a passing response, `mock_resp.json.return_value` must return a dict matching
the expected format:
- Chat: `{"choices": [{"message": {"content": "hello"}}]}`
- Raw: `{"response": "hello"}`

**ModelRouter construction:** The router loads `model_config.json` on init. Tests use the
existing `router` fixture from `test_model_router.py` (already returns a live `ModelRouter()`).
The HTTP fallback is only reached when the local llama_cpp path fails or the task routes
to an HTTP endpoint — tests invoke `_http_fallback()` directly to isolate it.

**Private method access:** `_http_fallback(task, messages, max_tokens, temperature)` is a
private method. Tests call it directly (`router._http_fallback(...)`) — acceptable for
unit testing internal behavior that has no other seam.

## Files Changed

| File | Change |
|------|--------|
| `tests/test_model_router.py` | Add 3 tests inside a new `TestHttpFallbackSizeLimit` class |

No implementation files change. No new dependencies.

## Acceptance Criteria

- [ ] `pytest tests/test_model_router.py::TestHttpFallbackSizeLimit -v` — 3/3 pass
- [ ] `pytest tests/test_model_router.py -v` — all existing tests still pass
- [ ] `pre-commit run --files tests/test_model_router.py` — all hooks pass
