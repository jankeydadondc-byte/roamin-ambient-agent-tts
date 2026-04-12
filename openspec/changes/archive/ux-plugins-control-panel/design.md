# UX & Plugins Control Panel — Design

Goal
----

Provide a compact desktop Control Panel for Roamin to monitor status, view logs, manage models, install/manage plugins, inspect task history, and perform start/stop/reload operations.

Scope (MVP)
------------

- Dashboard (status, quick actions)
- Logs tailing (live)
- Models list + basic controls
- Plugins list + install/uninstall + capability-grant flow
- Task history list + basic replay controls
- Settings (port discovery, auth)

Architecture Decisions
----------------------

- Frontend: SPA-first (Vite + React) for fast iteration; bundle into Tauri for desktop distribution.
- Control API: FastAPI with OpenAPI spec. Serve REST endpoints + a WebSocket `/ws/events` for live events.
- Event channel: WebSocket (bidirectional, low-latency). UI subscribes to `/ws/events` for updates (log lines, status, task updates).
- Port discovery: Control API writes an atomic `control_api_port.json` in the app docs directory (or `.loom/`) with `{port,pid,started_at}`. UI uses discovery file as primary source and falls back to configured port range (8765-8775).
- Plugin runtime: Subprocess isolation using JSON-RPC over stdio or a local socket. Plugins declare a manifest with `requestedCapabilities` and `entrypoint`.
- Plugin install UX: UI shows plugin manifest and requested capabilities; explicit admin confirmation required before granting any capabilities.
- Replay policy: Default to re-synthesize audio on replay; make configurable per-task.

Security & Safety
-----------------

- Discovery file must be written atomically and with restrictive ACLs.
- Plugin installs must be validated; run plugins with limited filesystem/network capabilities. Prefer per-plugin capability manifest enforcement.
- Control API endpoints that mutate state require authenticated/authorized access.

Acceptance Criteria
-------------------

- `tasks.md` lists prioritized implementation tasks with clear acceptance criteria.
- `spec.md` contains an initial OpenAPI-style endpoint list and WebSocket event schema.
- UI can discover Control API by reading the discovery file and connecting to `/ws/events`.

Notes
-----

This change targets the MVP subset only. Heavy editors, integrated terminals, and advanced plugin sandboxing are deferred to later iterations.
