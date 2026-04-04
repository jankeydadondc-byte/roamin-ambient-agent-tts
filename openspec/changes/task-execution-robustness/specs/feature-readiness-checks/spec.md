# Spec: Feature Readiness Checks

## Requirements

### R1 — Vision readiness check
`_check_feature_ready("vision")` returns `(False, <message>)` if PIL is not importable.

### R2 — Vision mmproj check
`_check_feature_ready("vision")` returns `(False, <message>)` if `QWEN3_VL_8B_MMPROJ` is `None`.

### R3 — Default capability always passes
`_check_feature_ready("default")` always returns `(True, "")` without probing any imports.

### R4 — Failed readiness halts run()
When `_check_feature_ready` returns `(False, msg)`, `run()` returns immediately with
`status="failed"` and `error=<msg>` — no screen observation, no planning, no tool execution.

### R5 — Readiness message is TTS-safe
The failure message is a complete English sentence with no markdown, no code, no brackets.

---

## Scenarios

### Scenario 1: PIL missing
```
GIVEN PIL is not installed (importlib.import_module("PIL") raises ImportError)
WHEN _check_feature_ready("vision") is called
THEN it returns (False, "Vision is unavailable: Pillow is not installed.")
```

### Scenario 2: mmproj constant is None
```
GIVEN PIL is importable
AND agent.core.llama_backend.QWEN3_VL_8B_MMPROJ is None
WHEN _check_feature_ready("vision") is called
THEN it returns (False, "Vision is unavailable: the multimodal projection file is missing.")
```

### Scenario 3: both dependencies present
```
GIVEN PIL is importable
AND QWEN3_VL_8B_MMPROJ is a non-None path
WHEN _check_feature_ready("vision") is called
THEN it returns (True, "")
```

### Scenario 4: non-vision task type bypasses all checks
```
GIVEN task_type is "default"
WHEN _check_feature_ready("default") is called
THEN it returns (True, "") without importing PIL or accessing llama_backend
```

### Scenario 5: run() stops on failed readiness
```
GIVEN _check_feature_ready("vision") returns (False, "Vision is unavailable: ...")
WHEN AgentLoop.run("what's on my screen") is called
THEN result["status"] == "failed"
AND result["error"] == "Vision is unavailable: ..."
AND ScreenObserver.observe() is never called
AND _generate_plan() is never called
```
