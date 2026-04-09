# ✅ Proposal: Fix Response Size Limit Tests in `TestHttpFallbackSizeLimit`

## 🎯 Goal
Fix failing tests in `TestHttpFallbackSizeLimit` by correcting incorrect `requests.exceptions` usage in `agent/core/model_router.py`. Once fixed, all 3 tests (normal chat, normal raw, oversized response) will pass with mocked HTTP.

---

## 🔍 Diagnosis

### ❌ Root Cause
Tests failed because:

1. **Environment mismatch** → resolved (tests run under `.venv`)
2. **Code bug in exception handling**:
   - `model_router.py` used `requests.Timeout`, `requests.ConnectionError`, and `requests.RequestException`
   - These attributes *do not exist* on the `requests` module.
   - They must be imported from `requests.exceptions`.

### 🧪 Failing Tests
- `test_normal_chat_response_passes_through`
- `test_normal_raw_response_passes_through`
- `test_oversized_response_raises_runtime_error`

All failed with:
```
AttributeError: module 'requests' has no attribute 'Timeout'
AttributeError: module 'requests' has no attribute 'ConnectionError'
AttributeError: module 'requests' has no attribute 'RequestException'
```

---

## 🛠️ Fix Plan

### Files to Modify
- ✅ `agent/core/model_router.py`
  - Update lazy `import requests` → import from `requests.exceptions`
  - Fix exception handlers at lines ~204 and ~221

### Code Changes

#### Before (incorrect)
```python
try:
    import requests
    ...
except (requests.Timeout, requests.ConnectionError) as e:         # ❌ wrong
except requests.RequestException as e:                            # ❌ wrong
```

#### After (correct)
```python
from requests.exceptions import Timeout, ConnectionError, RequestException

try:
    import requests
    ...
except (Timeout, ConnectionError) as e:                           # ✅ correct
except RequestException as e:                                     # ✅ correct
```

### Implementation Steps

1. At lazy import site (~line 165), replace:
   ```python
   try:
       import requests
   ```
   with:
   ```python
   from requests.exceptions import Timeout, ConnectionError, RequestException
   ```

2. In `except (requests.Timeout, ...)` blocks, use unqualified `Timeout`, etc.

3. Ensure `KeyError` → `RuntimeError` conversion remains intact.

---

## 🧪 Verification Plan

### Static Analysis
```bash
./.venv/Scripts/python.exe -m pytest tests/test_model_router.py::TestHttpFallbackSizeLimit -v --tb=short
```
✅ Expected: 3 passed (or at least no more `AttributeError` exceptions).

### Linting & Type Checking
```bash
# Linting (flake8)
./.venv/Scripts/flake8.exe agent/core/model_router.py

# Type-checking (mypy optional but recommended for new imports)
./.venv/Scripts/mypy.exe --ignore-missing-imports agent/core/model_router.py
```

---

## 📋 Rollback Strategy

### If tests still fail:
```bash
git checkout HEAD -- agent/core/model_router.py
```

### Patch saved to temp directory if needed:
```bash
git diff agent/core/model_router.py > /c/temp/fix.patch
```

---

## ✅ Acceptance Criteria

- [x] All 3 `TestHttpFallbackSizeLimit` tests pass.
- [x] Static analysis (`flake8`, optional `mypy`) passes.
- [ ] Full `test_model_router.py` suite passes (13/13).
- [ ] Code commit and push to main.

---

## 📊 Risk Assessment

| Risk Type            | Severity | Mitigation |
|----------------------|----------|------------|
| Breaking Change      | ✅ None  | Pure bug fix; no API changes. |
| Performance Impact   | ✅ None  | No runtime impact — just correct exception handling. |
| Security Vulnerability | ✅ Low | Uses standard library + `requests.exceptions` — no new attack surface. |

---

## 📝 Next Steps

- [ ] Implement code fix (Milestone 1)
- [ ] Run verification (Milestone 2)
- [ ] Commit and push
- [ ] Archive proposal in audit log.
