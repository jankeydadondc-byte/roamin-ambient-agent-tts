# Roamin Control Panel — Design Doc

Date: 2026-04-04
Author: GitHub Copilot (acting as design/PM)

Goal
----

Provide a compact desktop Control Panel for Roamin to monitor status, view logs, manage models, install/manage plugins, inspect task history, and perform start/stop/reload operations. Target final delivery as a Tauri desktop app; develop as a browser SPA (Vite + React) first for fast iteration.

MVP Scope (first release)
-------------------------

- Dashboard: agent health, loaded model, GPU usage, current task, uptime, last wake time.
- Logs: tail view (server-side tail), level filter, search, copy/export.
- Models: list available models, load/unload, discovery status, manual "scan models" action.
- Plugins: installed list, enable/disable, install (upload .zip or git URL), show requested capabilities and metadata, require admin confirmation.
- Task History: list of previous tasks with timestamps, status, short transcript, ability to replay TTS (re-synthesize by default).
- Settings: control API discovery (dynamic port file), auth token management, retention policies, experimental flags.

Non-functional goals
--------------------

- Local-only by default (listen on loopback). No remote binding unless explicitly configured.
- Use dynamic port detection (never hard-code ports). Launcher writes `control_api.json` with port + token for UI discovery.
- Responsive UI, accessible (keyboard nav + ARIA), contrast-compliant.
- Security: admin actions require token; plugin installs require explicit grant.

Architecture & Runtime
----------------------

- Frontend: Vite + React (SPA) during development. Wrap into Tauri for final native desktop app.
- Backend: `FastAPI` process run separately (supervised by the current launcher). It exposes the OpenAPI spec and a WebSocket endpoint for live events.
- Discovery: control API writes `logs/control_api.json` with {pid, port, token} for the UI and launcher to discover.
- IPC: Plugins run as subprocesses using JSON-RPC over stdio/sockets for isolation.

Pages & Components
------------------

- App Shell
  - Side navigation: Dashboard, Logs, Models, Plugins, Tasks, Settings
  - Header: agent name, status indicator, small metrics (uptime, wake count)
  - Global search (logs + tasks)

- Dashboard
  - Status card (Up/Degraded/Down), last wake, model name
  - GPU card: VRAM used/free, current model VRAM
  - Recent activity: last 5 tasks with outcomes
  - Quick actions: Start, Stop, Restart, Scan Models

- Logs
  - Live tail (WebSocket) with auto-scroll toggle
  - Filters: level (DEBUG/INFO/WARNING/ERROR), component (agent/llama/tts), text search
  - Export button (download tail or full file)

- Models
  - List: model name, source (local/lmstudio/ollama), size, mmproj present
  - Actions: Load, Unload, Set Default, Show Path
  - Auto-scan button and last-scan timestamp

- Plugins
  - Installed list with enable/disable switch, version, capabilities
  - Install modal: upload ZIP or provide git URL, show parsed manifest and requested capabilities, confirm install (admin token prompt)
  - Plugin details: logs, actions provided, health

- Tasks / History
  - Timeline: timestamp, short transcript, status badges (completed/failed/cancelled)
  - Details view: full transcript, model used, steps, TTS audio (re-synthesize by default, option to store audio)
  - Re-run button (re-queue task) — requires confirmation

- Settings
  - Control API discovery info (path to `control_api.json`), token management
  - Auth settings: enable OS-integrated auth, token fallback
  - Retention: logs retention days, task history retention
  - Advanced: toggle features (plugin sandbox mode)

Wireframes (ASCII sketches)
---------------------------

Dashboard (desktop wide)

```
--------------------------------------------------------------
| Roamin Control Panel   | Status: UP | GPU: 15.6GB free |  Uptime |
|------------------------------------------------------------|
| [Status card] [GPU card] [Recent tasks card]  [Quick actions]
|                                                            |
| [Logs tail (collapsible)]                                  |
--------------------------------------------------------------
```

Plugins page

```
--------------------------------------------------------------
| Plugins | [Install] [Refresh]                               |
|------------------------------------------------------------|
| Name | Version | Enabled | Capabilities | Actions (Logs/Details) |
| Plugin A | 0.1.2 | ✅ | network,filesystem | [Disable][Logs]     |
| Plugin B | 0.1.0 | ❌ | none | [Enable][Details]                   |
--------------------------------------------------------------
```

Component Inventory
-------------------

- `StatusCard`, `MetricCard` (GPU/CPU), `LogTail`, `ModelCard`, `PluginList`, `PluginInstallModal`, `TaskTimeline`, `AudioPlayer`, `ConfirmModal`, `TokenPrompt`.

Accessibility & UX Checklist
---------------------------

- Keyboard navigable: all controls reachable by Tab/Shift+Tab
- ARIA roles for lists and buttons
- Color contrast ≥ AA for text and key UI elements
- Focus visible outlines on interactive elements
- Screen-reader friendly labels for cards and controls

Security & Privacy
------------------

- Control API binds to loopback; port selected dynamically; discovery file `logs/control_api.json` created with strict ACL (user-only) by launcher.
- Admin operations require entering the admin token.
- Plugins request capabilities in manifest; install UI shows requested capabilities and requires explicit grant.
- Task history may contain PII — provide settings to redact or limit retention.

Acceptance Criteria
-------------------

- The SPA dev server renders Dashboard + Logs + Plugins with mock data.
- `GET /status` and `GET /models` return realistic JSON in API skeleton.
- Plugin install modal parses a sample `plugin_manifest.yaml` and displays capabilities.
- WebSocket events deliver log lines to the UI in real time.
- All admin actions require token confirmation.

Open Questions / Decisions Needed (short list)
---------------------------------------------

1. Live events: you've leaned toward WebSocket — confirm for logs/status and plugin messages (WebSocket allows bidirectional control). If yes, we'll design `/ws/events`.
2. Plugin IPC: default to subprocess JSON-RPC — confirm.
3. Task audio replay: store synthesized audio by default (fast replay) or re-synthesize on-demand? (recommended: re-synthesize; opt-in store)
4. Reuse `os_agent` UI: confirm permission to scan and evaluate `C:\AI\os_agent\ui\roamin-control` for reuse.

Next steps (short)
------------------

1. If you confirm WebSocket + subprocess plugins + re-synthesize-on-replay preference, I will draft the `OpenAPI` spec and a `FastAPI` skeleton (`agent/control_api.py`) with dynamic port discovery and a minimal `/status`, `/models`, `/plugins`, `/task-history`, and a `/ws/events` WebSocket.
2. I can also scan `C:\AI\os_agent\ui\roamin-control` for reuse feasibility and report back.

Files created
-------------

- `docs/control_panel_design.md` (this file)

Questions for you (short)
------------------------

- Confirm WebSocket for live events? (Yes/No)
- Confirm plugin IPC as subprocess JSON-RPC? (Yes/No)
- Confirm replay policy: re-synthesize on-demand (default) or store audio by default? (re-synthesize/store)
- Allow me to scan `C:\AI\os_agent\ui\roamin-control` for potential reuse? (Yes/No)
