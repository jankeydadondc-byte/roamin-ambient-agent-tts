# Priority 10: Documentation & Onboarding

**Status:** DRAFT
**Date:** 2026-04-10
**Scope:** Close the gap between working code and usable documentation — for the
developer (future-you returning after months away) and for any future contributor.

---

## Background

As of 2026-04-10, Roamin is feature-complete across 9 priorities:

- Voice pipeline, vision, task execution, plugin system, security, Control Panel UI,
  persistent memory (SQLite + ChromaDB + MemPalace), structured logging, 53 passing tests

What's missing is everything a human needs to *understand, configure, extend, or debug*
the system from scratch. The README is 40 lines. `docs/` has one design note. Plugin
development requires reading two source files and guessing. The troubleshooting story
is "check roamin.log and hope."

This proposal delivers four targeted documents plus a thin Control Panel help tab —
enough to fully onboard a new contributor or confidently return after 6 months away.

---

## What Already Exists (Do Not Duplicate)

| Already there | Location |
|---|---|
| Architecture overview (verbose) | `MASTER_CONTEXT_PACK.md` |
| API spec + OpenAPI | `openspec/changes/archive/ux-plugins-control-panel/` |
| Control panel design notes | `docs/control_panel_design.md` |
| Plugin example | `agent/plugins/example_ping.py` |
| .env variable list | `.env.example` |
| Control Panel UI README | `ui/control-panel/README.md` |

None of the above are user-facing onboarding docs. They are developer working notes.

---

## Milestone 10.1 — Root README Rewrite

**File:** `README.md`
**Current state:** 40 lines, covers setup and wake word only
**Effort:** LOW (30 min)

Rewrite to cover:

1. **What it is** — one paragraph, non-technical
2. **System requirements** — Python 3.12, Windows 10/11, RTX GPU, CUDA, VS Build Tools
3. **First-time setup** — ordered steps: clone → venv → pip install → llama-cpp-python
   (link to `docs/SETUP.md` for detail)
4. **Starting Roamin** — `python launch.py` (preferred) vs `.vbs` shortcuts
5. **Using it** — `ctrl+space` → speak → what happens
6. **Control Panel** — `http://localhost:5173`, what each tab does (one line each)
7. **Configuration** — `.env.example` → `.env`, key variables called out
8. **Extending** — "to add a plugin, see `docs/PLUGIN_DEVELOPMENT.md`"
9. **Troubleshooting** — "see `docs/TROUBLESHOOTING.md`"
10. **Project layout** — 10-line tree of top-level directories with one-line descriptions

**Acceptance:** Someone who has never seen the project can clone, install, and run it
using only `README.md` and the linked docs.

---

## Milestone 10.2 — Setup Guide

**File:** `docs/SETUP.md`
**Current state:** Does not exist
**Effort:** LOW–MEDIUM (45 min)

Step-by-step environment setup for a clean Windows machine.

### Sections:

**Prerequisites**
- Python 3.12 (link to python.org), verify with `python --version`
- Node.js 18+ (for Control Panel dev server), `node --version`
- CUDA Toolkit 12.x (link to NVIDIA)
- VS 2019 Build Tools with "Desktop development with C++" workload

**Python environment**
```powershell
cd C:\AI\roamin-ambient-agent-tts
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**llama-cpp-python (CUDA build)**
- Reference `scripts/install_llama_cpp_cuda.ps1`
- Document the flags: `CMAKE_ARGS`, `FORCE_CMAKE`, expected output

**MemPalace (semantic memory)**
- Already installed via requirements.txt
- Palace initialized at `mem_palace_data/` — run `mempalace mine .` to re-index after
  adding new files

**Environment configuration**
- Copy `.env.example` → `.env`
- Required: nothing (all defaults work locally)
- Optional: `ROAMIN_CONTROL_API_KEY` for auth, `LM_API_TOKEN` for LM Studio

**Model setup**
- Where `model_config.json` lives, what fields it has
- How to add a new model (name, path, context_length)
- `ModelRouter` picks model by task type automatically

**Verify the install**
```powershell
python -c "from agent.core.memory import MemoryManager; print('OK')"
python run_control_api.py  # should print "Uvicorn running on http://127.0.0.1:8765"
```

**First run**
```powershell
python launch.py
# → opens Control API + wake listener + Vite dev server
```

---

## Milestone 10.3 — Plugin Development Guide

**File:** `docs/PLUGIN_DEVELOPMENT.md`
**Current state:** Does not exist (reader must reverse-engineer `example_ping.py`)
**Effort:** LOW (30 min)

### Sections:

**What a plugin is**
- A `.py` file in `agent/plugins/` with a class named `Plugin`
- Auto-discovered on startup — no wiring required
- Gets `on_load(registry)` called once; registers tools into the tool registry

**Minimal plugin template** (annotated)
```python
# agent/plugins/my_plugin.py
class Plugin:
    name = "my_plugin"                    # unique, snake_case

    def on_load(self, registry) -> None:
        registry.register(
            name="my_tool",               # what the LLM calls
            description="...",            # shown to the planner
            risk="low",                   # low | medium | high (high = HITL approval)
            params={"input": "str"},      # parameter schema
            implementation=self._run,
        )

    def on_unload(self) -> None:
        pass                              # cleanup — close connections, stop threads

    def _run(self, params: dict) -> dict:
        return {"result": params["input"].upper()}
```

**Risk levels**
| Level | Behaviour |
|-------|-----------|
| `low` | Executes immediately |
| `medium` | Executes immediately (logged to audit log) |
| `high` | Pauses — sends approval toast to Control Panel; waits for user approve/deny |

**Tool registry API** — what `registry.register()` accepts, what `list_tools()` returns

**Disabling a plugin without deleting it**
- Rename to `_my_plugin.py` (leading underscore — excluded by loader)

**Testing your plugin**
```python
from agent.plugins.my_plugin import Plugin
from agent.core.tool_registry import ToolRegistry

r = ToolRegistry()
Plugin().on_load(r)
assert "my_tool" in r.list_tools()

result = r.execute("my_tool", {"input": "hello"})
assert result["result"] == "HELLO"
```

**Real examples to read**
- `agent/plugins/example_ping.py` — minimal working plugin
- `agent/plugins/mempalace.py` — subprocess + ImportError handling + Phase 2 MCP server

---

## Milestone 10.4 — Troubleshooting Guide

**File:** `docs/TROUBLESHOOTING.md`
**Current state:** Does not exist
**Effort:** LOW (30 min)

Captures every recurring issue encountered during development so future-you doesn't
re-debug from scratch.

### Structure: symptom → cause → fix

**Agent won't start**
- `keyboard` import error → run as administrator (keyboard hook requires elevated perms)
- `llama-cpp-python` crash on import → CUDA build not installed; run `scripts/install_llama_cpp_cuda.ps1`
- Port 8765 already in use → another Control API process running; find PID with `netstat -ano | findstr 8765`

**Wake word doesn't trigger**
- Hotkey `ctrl+space` intercepted by another app → check what's bound to it in Windows settings
- Audio device wrong → check `sounddevice.query_devices()`, set `ROAMIN_AUDIO_DEVICE` env var

**Control Panel shows "disconnected"**
- Control API not running → start `run_control_api.py` or use `launch.py`
- Port mismatch → `window.__CONTROL_API_URL__` in `ui/control-panel/index.html` vs actual port

**Task History shows no tasks**
- SQLite DB not created yet → run one task first; DB is created on first use
- DB path wrong → default is `./roamin.db` (project root); confirm with `ls *.db`

**LM Studio model not appearing in Control Panel**
- `model_config.json` not saved → file must exist at project root
- LM Studio not running → `ModelRouter` falls back to llama-cpp-python; this is expected

**MemPalace search returns nothing**
- Palace not mined → run `mempalace mine .` from project root to index files
- Wrong palace path → check `ROAMIN_MEMPALACE_PATH` env var (default: `mem_palace_data/`)

**Tests failing after code changes**
```powershell
# Run unit tests only (no server needed):
.venv\Scripts\python -m pytest tests/unit/ -q

# Run with verbose output for a specific failing test:
.venv\Scripts\python -m pytest tests/unit/test_control_api.py -v
```

**Checking logs**
| Log | Location | Contains |
|-----|----------|----------|
| Agent main log | `roamin.log` | All INFO+ from wake listener + AgentLoop |
| Control API | printed to terminal | FastAPI startup, request errors |
| MemPalace MCP | `logs/mempalace_mcp.log` | MCP server output (only in `auto`/`standalone` mode) |
| Audit log | `logs/audit.log` | HIGH-risk tool executions |

---

## Milestone 10.5 — Control Panel Help Tab

**File:** `ui/control-panel/src/components/Help.jsx` (new)
**Current state:** No in-app help exists; users must leave the UI to read docs
**Effort:** LOW (30 min)

A static JSX component wired into the Sidebar nav as a "Help" section. No fetch calls,
no backend. Renders:

- **Voice commands** — list of trigger phrases Roamin understands (direct dispatch + examples)
- **Control Panel tabs** — one sentence per tab explaining what it shows
- **Keyboard shortcuts** — `ctrl+space` (wake), `Escape` (dismiss toast)
- **Quick links** — relative paths to `docs/SETUP.md`, `docs/PLUGIN_DEVELOPMENT.md`, `docs/TROUBLESHOOTING.md`
- **Version info** — pulled from `package.json` via `import pkg from '../../package.json'`

Wired into `App.jsx` under a "Help" nav entry (last in sidebar, below Tasks).

---

## Files Created / Modified

| File | Action |
|------|--------|
| `README.md` | REWRITE — full onboarding entry point |
| `docs/SETUP.md` | CREATE — step-by-step environment setup |
| `docs/PLUGIN_DEVELOPMENT.md` | CREATE — plugin authoring guide + annotated template |
| `docs/TROUBLESHOOTING.md` | CREATE — symptom → cause → fix for known issues |
| `ui/control-panel/src/components/Help.jsx` | CREATE — in-app static help panel |
| `ui/control-panel/src/App.jsx` | MODIFY — add Help to sidebar nav |

---

## What This Explicitly Does NOT Include

- Video tutorials (out of scope for a personal tool)
- API reference site / auto-generated docs (MASTER_CONTEXT_PACK.md covers this)
- Changelog / RELEASE_NOTES.md (low value for a private repo with one contributor)
- Tooltip overlays on every UI element (over-engineered; Help tab is sufficient)
- External hosting (no GitHub Pages, no Docusaurus)

---

## Acceptance Criteria

- `README.md` alone is sufficient for a first-time setup attempt
- `docs/PLUGIN_DEVELOPMENT.md` alone is sufficient to write and load a working plugin
- `docs/TROUBLESHOOTING.md` covers every issue encountered during development of Priorities 1–9
- Control Panel Help tab renders without errors and answers "what does this button do?"
- All 53 existing tests still pass after App.jsx change

---

## Implementation Order

1. **10.4 — Troubleshooting** (zero risk, pure writing, highest day-to-day value)
2. **10.3 — Plugin guide** (low risk, directly enables future plugins)
3. **10.2 — Setup guide** (low risk, fills the biggest onboarding gap)
4. **10.1 — README rewrite** (depends on 10.2 and 10.3 existing to link to)
5. **10.5 — Help tab** (only code change; do last to avoid JS churn while writing)
