# Proposal: Full Codebase Triage — Code Triage & Analysis Agent v12

## Why

Roamin has reached a stable multi-phase milestone. The voice pipeline, MemPalace integration,
unified chat engine, plugin system, Control Panel, and security hardening are all in place.
Before adding new capabilities (ambient presence, P11+), the codebase should be systematically
audited to surface bugs, architectural drift, dead code, and hidden risks that have accumulated
across the build.

The audit uses the **Code Triage & Analysis Agent v12** skill (`anthropic-skills:code-triage-agent`),
invoked once per file in priority order. Each file gets its own triage pass — findings are
documented in `findings.md` as the run progresses, giving a living record that can drive
follow-up work.

This is a read-only diagnostic run. No fixes are applied during the triage itself. Findings
are classified, weighted, and queued for a separate remediation pass.

## What This Is Not

- Not a refactor. No code is changed.
- Not a feature. Nothing new is added.
- Not a one-shot "check everything at once." Each file is triaged in isolation with full
  attention, following the v12 structured method.

## Audit Scope

Every file in `agent/` and `ui/control-panel/src/` is in scope, plus `launch.py`,
`requirements.txt`, and the test suite. The following are explicitly excluded:

- `N.E.K.O./` — unrelated project, never touch
- `framework/` — unrelated project, never touch
- `models/` — binary model weights, not auditable
- `mem_palace_data/` — runtime database, not auditable
- `observations/` — screenshot cache, not auditable
- `logs/` — runtime logs, not auditable

## File Audit Order

Files are ordered by blast radius: the files where a hidden bug does the most damage come
first. Within a tier, larger/more complex files come before smaller ones.

### Tier 1 — Entry Points & Core Loop (highest blast radius)

| # | File | Why |
|---|------|-----|
| 1 | `launch.py` | Bootstraps every component; startup bugs block everything |
| 2 | `agent/core/agent_loop.py` | Step executor; errors here silently corrupt every task |
| 3 | `agent/core/config.py` | Config loaded at startup; bad defaults cascade everywhere |
| 4 | `agent/core/paths.py` | Path resolution used by every file I/O operation |

### Tier 2 — Voice Pipeline (critical user-facing path)

| # | File | Why |
|---|------|-----|
| 5 | `agent/core/voice/wake_listener.py` | Primary hotkey entrypoint; 41k lines, highest complexity |
| 6 | `agent/core/chat_engine.py` | Unified brain — both voice and chat route through here |
| 7 | `agent/core/voice/stt.py` | STT; transcription errors corrupt all downstream context |
| 8 | `agent/core/voice/tts.py` | TTS output layer; failures are user-visible immediately |
| 9 | `agent/core/voice/session.py` | Session state; state drift causes garbled multi-turn context |
| 10 | `agent/core/voice/wake_word.py` | Wake word detection; false positives/negatives affect UX |

### Tier 3 — Inference & Model Layer

| # | File | Why |
|---|------|-----|
| 11 | `agent/core/model_router.py` | Model selection & fallback; wrong routing = wrong model silently |
| 12 | `agent/core/llama_backend.py` | Local LLM inference; GPU/memory bugs here are hard to catch |
| 13 | `agent/core/model_sync.py` | Auto-sync from LM Studio; sync bugs cause stale model config |
| 14 | `agent/core/model_config.json` | Model definitions; misconfigured entries cause silent fallbacks |
| 15 | `agent/core/context_builder.py` | Context assembly; token overflow or truncation errors here |
| 16 | `agent/core/system_prompt.txt` | System prompt; prompt injection surface, logic gaps |

### Tier 4 — Tool System

| # | File | Why |
|---|------|-----|
| 17 | `agent/core/tool_registry.py` | Tool registration & approval gates; bypass here = security hole |
| 18 | `agent/core/tools.py` | Tool implementations; path traversal, injection, silent failures |
| 19 | `agent/core/validators.py` | Path & input validation; gaps here directly enable unsafe ops |
| 20 | `agent/core/audit_log.py` | Audit trail; silent failures mean tool ops go unrecorded |
| 21 | `agent/core/secrets.py` | Credential management; leakage or missing validation |

### Tier 5 — Memory & Observation

| # | File | Why |
|---|------|-----|
| 22 | `agent/core/memory/memory_store.py` | SQLite + ChromaDB; data loss, corruption, threading bugs |
| 23 | `agent/core/memory/memory_manager.py` | Memory ops coordinator; read/write consistency |
| 24 | `agent/core/memory/memory_search.py` | Semantic search; relevance bugs affect recall quality |
| 25 | `agent/core/observation.py` | Screen capture & OCR; resource leaks, privacy surface |
| 26 | `agent/core/screen_observer.py` | Screen capture driver; same surface as observation.py |
| 27 | `agent/core/observation_scheduler.py` | Scheduled captures; scheduling drift, missed stops |
| 28 | `agent/core/proactive.py` | Proactive suggestions; runaway loops, false triggers |

### Tier 6 — Plugin System

| # | File | Why |
|---|------|-----|
| 29 | `agent/plugins/__init__.py` | Plugin loader & auto-discovery; bad plugin = agent crash |
| 30 | `agent/plugins/mempalace.py` | MemPalace plugin; MCP wiring, data consistency |

### Tier 7 — Control API & UI

| # | File | Why |
|---|------|-----|
| 31 | `agent/control_api.py` | FastAPI server; WebSocket leaks, auth gaps, endpoint errors |
| 32 | `ui/control-panel/src/App.jsx` | Main shell; state management, WebSocket lifecycle |
| 33 | `ui/control-panel/src/apiClient.js` | WS/HTTP client; reconnect logic, error swallowing |
| 34 | `ui/control-panel/src/components/TaskHistory.jsx` | Task log; rendering performance, data binding |
| 35 | `ui/control-panel/src/components/Sidebar.jsx` | Nav/status; stale state indicators |

### Tier 8 — Supporting Modules & Infrastructure

| # | File | Why |
|---|------|-----|
| 36 | `agent/core/roamin_logging.py` | Logging setup; misconfigured = lost diagnostics |
| 37 | `agent/core/async_utils.py` | Async helpers; deadlock and race condition surface |
| 38 | `agent/core/resource_monitor.py` | GPU/CPU tracking; runaway polling, missing teardown |
| 39 | `agent/core/diagnostics.py` | Health checks; false-positive clears mask real problems |
| 40 | `agent/core/tray.py` | Windows tray icon; threading, crash-on-exit edge cases |
| 41 | `agent/core/ports.py` | Port definitions; conflicts, hardcoded assumptions |
| 42 | `requirements.txt` | Dependency audit; unpinned versions, abandoned packages |

### Tier 9 — Test Suite

| # | File | Why |
|---|------|-----|
| 43 | `tests/test_e2e_smoke.py` | E2E smoke; false passes that mask real failures |
| 44 | `tests/test_approval_gates.py` | Security tests; incomplete coverage = false confidence |
| 45 | `tests/test_model_router.py` | Router tests; missing fallback scenarios |
| 46 | `tests/test_memory_module.py` | Memory tests; concurrent access not tested |
| 47 | `tests/test_control_api.py` | API tests; WebSocket lifecycle, auth checks |
| 48 | Remaining test files | Coverage gaps, mock fidelity |

## Output Format

Findings are appended to `findings.md` in this directory as each file is triaged.
Each entry follows this template:

```
## [##] path/to/file.py

**Triage date:** YYYY-MM-DD
**v12 severity verdict:** critical | high | medium | low | clean

### Findings

#### [SEVERITY] Short title
- **Location:** function/line
- **Description:** What the issue is
- **Risk:** What goes wrong if unfixed
- **Suggested fix:** One-line direction (not implementation)

### Notes
Any architectural observations not captured as discrete findings.
```

Severity definitions:
- **critical** — can cause data loss, security bypass, or agent crash in normal use
- **high** — causes incorrect behavior or silent failures in edge cases
- **medium** — code smell, maintainability risk, or missing safety net
- **low** — style, naming, minor optimization

## Execution

Each file is triaged by invoking the `anthropic-skills:code-triage-agent` skill (v12),
reading the full file first, then running the structured triage prompt. One file per session
segment. The operator (Claude) reads the file, runs the v12 analysis, writes findings, then
moves to the next file.

The triage run is complete when all Tier 1–8 files have an entry in `findings.md`.
The test suite (Tier 9) is triaged last as a coverage-gap audit rather than a code-bug audit.

## Success Criteria

- Every in-scope file has a findings entry (even if verdict is "clean")
- All critical and high findings have a suggested fix direction
- A remediation tasks list exists at the end of `findings.md` with findings grouped by
  priority, ready to feed into the next openspec phase
