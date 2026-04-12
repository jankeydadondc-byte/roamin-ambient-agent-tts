# Tasks — Priority 10: Documentation & Onboarding

## Status

✅ **ALL COMPLETE** (2026-04-10)

Implementation order completed: 10.4 → 10.3 → 10.2 → 10.1 → 10.5

---

## 10.1 — Root README Rewrite

**File:** `README.md`
**Effort:** LOW (~30 min)
**Status:** ✅ COMPLETE

- [x] What it is (one paragraph, non-technical)
- [x] System requirements (table with OS, Python, GPU, CUDA)
- [x] First-time setup (3 steps, links to docs/SETUP.md)
- [x] Starting Roamin (`launch.py` preferred)
- [x] Using it (voice command flow + table of example phrases)
- [x] Control Panel overview (tab descriptions + links)
- [x] Configuration (.env.example callout + key variables table)
- [x] Extending (plugin guide link + model config section)
- [x] Troubleshooting (link to full guide)
- [x] Project layout (12-line tree with descriptions)
- [x] Technologies table (why each chosen)
- [x] Status checklist (9 items all ✅)

---

## 10.2 — Setup Guide

**File:** `docs/SETUP.md`
**Effort:** LOW–MEDIUM (~45 min)
**Status:** ✅ COMPLETE

- [x] Prerequisites section (Python, Node, CUDA, VS Build Tools — 4 items with links)
- [x] Clone the repository (git command)
- [x] Python venv + pip install steps (activate + requirements.txt)
- [x] llama-cpp-python CUDA build (script reference + manual fallback)
- [x] MemPalace initialization (mine command + verify status)
- [x] Environment config (.env.example → .env with key variables table)
- [x] Model configuration (model_config.json with annotated JSON example)
- [x] Verification commands (8 check commands covering all layers)
- [x] First run section (Option A: launcher, Option B: manual 3 terminals)
- [x] Troubleshooting subsection (common setup errors + fixes)

---

## 10.3 — Plugin Development Guide

**File:** `docs/PLUGIN_DEVELOPMENT.md`
**Effort:** LOW (~30 min)
**Status:** ✅ COMPLETE

- [x] What a plugin is (5-point explanation + no-wiring guarantee)
- [x] Minimal annotated plugin template (50 lines, fully commented)
- [x] Tool registration reference (params table, risk levels)
- [x] Risk level table (low/medium/high → behaviour + when to use)
- [x] Tool implementation callable pattern (3 rules + example)
- [x] Multiple tools in one plugin (example with 2 tools)
- [x] Error handling & unavailability (graceful ImportError + service check)
- [x] Subprocess pattern (mempalace status example with timeout)
- [x] Disable without deleting (_prefix convention)
- [x] Testing your plugin (test pattern + 3 test functions)
- [x] Real examples to read (example_ping.py + mempalace.py with notes)
- [x] Common patterns (caching, configuration, subprocess management)
- [x] Checklist before shipping (13 items)
- [x] FAQ (how tools work, async, config, etc.)

---

## 10.4 — Troubleshooting Guide

**File:** `docs/TROUBLESHOOTING.md`
**Effort:** LOW (~30 min)
**Status:** ✅ COMPLETE

- [x] Agent won't start (3 subsections: keyboard perms, llama-cpp CUDA build, port 8765 conflict)
- [x] Wake word doesn't trigger (2 subsections: hotkey intercepted, wrong audio device)
- [x] Control Panel disconnected (3 subsections: API not running, port mismatch, dev server not running)
- [x] Task History empty (2 subsections: DB not created, wrong path)
- [x] LM Studio model not showing (2 subsections: model_config.json invalid, LM Studio not running)
- [x] MemPalace search empty (3 subsections: not mined, wrong path, package not installed)
- [x] Tests failing after changes (subprocess, import errors, timeout/hang)
- [x] Logs section (table of 4 log files + how to tail + search + clear)
- [x] Still stuck? (troubleshooting flow)

---

## 10.5 — Control Panel Help Tab

**Files:** `ui/control-panel/src/components/Help.jsx` (CREATE), `ui/control-panel/src/App.jsx` (MODIFY), `ui/control-panel/src/components/Sidebar.jsx` (MODIFY)
**Effort:** LOW (~30 min)
**Status:** ✅ COMPLETE

- [x] Help.jsx — voice commands list (5 phrases + descriptions)
- [x] Help.jsx — Control Panel tab descriptions (5 tabs)
- [x] Help.jsx — keyboard shortcuts (4 shortcuts: ctrl+space, Escape, arrows, Enter)
- [x] Help.jsx — quick links to docs (4 GitHub links to guides)
- [x] Help.jsx — version info (package.json reference + date)
- [x] Sidebar.jsx — add Help nav item (icon: "?", label: "Help", id: "help")
- [x] App.jsx — import Help component
- [x] App.jsx — wire Help section into right panel (last section before closing)
- [x] Verify 53 existing tests still pass after changes ✅

---

## Verification Results

```powershell
✅ Tests: 53 passed in 7.06s (0 failures, 0 warnings)
✅ All docs created and linked in README
✅ Help tab renders without errors
✅ No regressions in UI or backend
```

---

## Files Created / Modified

| File | Status |
|------|--------|
| `README.md` | ✅ REWRITTEN |
| `docs/SETUP.md` | ✅ CREATED |
| `docs/PLUGIN_DEVELOPMENT.md` | ✅ CREATED |
| `docs/TROUBLESHOOTING.md` | ✅ CREATED |
| `ui/control-panel/src/components/Help.jsx` | ✅ CREATED |
| `ui/control-panel/src/App.jsx` | ✅ MODIFIED (import + Help section) |
| `ui/control-panel/src/components/Sidebar.jsx` | ✅ MODIFIED (added Help nav item) |
| `openspec/changes/priority-10-docs-onboarding/proposal.md` | ✅ CREATED |
| `openspec/changes/priority-10-docs-onboarding/tasks.md` | ✅ CREATED (this file) |
