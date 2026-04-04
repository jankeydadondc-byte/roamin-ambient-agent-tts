# Spec: Tool Fallback Chains

## Requirements

### R1 — Primary tool success returns immediately
If the primary tool succeeds, no fallback is attempted and the result contains no `fallback_used`
key.

### R2 — Primary failure triggers first configured fallback
If the primary tool fails and a fallback chain is configured, the first fallback is attempted with
adapted params.

### R3 — First successful fallback is returned with fallback_used key
The result dict includes `"fallback_used": <fallback_tool_name>` to allow callers to log or adapt.

### R4 — All fallbacks exhausted returns original failure
If every fallback in the chain also fails, the original primary failure dict is returned (no
`fallback_used` key).

### R5 — Tool with no configured fallback returns failure directly
`execute("run_python", ...)` failing returns the failure immediately; no fallback loop runs.

### R6 — Param adapter is applied before calling fallback
The `_TOOL_FALLBACKS` lambda adapter transforms primary params into fallback-compatible params
before the fallback tool is called.

### R7 — _execute_single is independently testable
`registry._execute_single(name, params)` behaves identically to the previous `execute()` logic
(no fallback, no logging).

---

## Scenarios

### Scenario 1: web_search succeeds — no fallback
```
GIVEN web_search returns {"success": True, "result": "..."}
WHEN registry.execute("web_search", {"query": "dogs"}) is called
THEN the result is returned immediately
AND fetch_url is never called
AND result has no "fallback_used" key
```

### Scenario 2: web_search fails — fetch_url fallback fires
```
GIVEN web_search raises an exception (network error)
AND fetch_url returns {"success": True, "result": "<html>..."}
WHEN registry.execute("web_search", {"query": "dogs"}) is called
THEN fetch_url is called with {"url": "https://duckduckgo.com/?q=dogs"}
AND result == {"success": True, "result": "<html>...", "fallback_used": "fetch_url"}
```

### Scenario 3: all fallbacks fail — original failure returned
```
GIVEN web_search fails
AND fetch_url also fails
WHEN registry.execute("web_search", {"query": "dogs"}) is called
THEN the original web_search failure dict is returned
AND result has no "fallback_used" key
```

### Scenario 4: tool with no fallback returns failure directly
```
GIVEN run_python is not in _TOOL_FALLBACKS
AND run_python raises SyntaxError
WHEN registry.execute("run_python", {"code": "not valid"}) is called
THEN the failure dict is returned
AND no other tools are attempted
```

### Scenario 5: memory_recall falls back to memory_search
```
GIVEN memory_recall fails (fact not found)
AND memory_search returns {"success": True, "result": "..."}
WHEN registry.execute("memory_recall", {"fact_name": "my age"}) is called
THEN memory_search is called with {"query": "my age"}
AND result contains "fallback_used": "memory_search"
```
