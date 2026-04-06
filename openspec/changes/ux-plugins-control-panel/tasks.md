# Tasks — UX & Plugins Control Panel (prioritized)

Priority order (most → least important)

1. Define Control API Spec (in-progress)
   - Rationale: API contract is required before backend/frontend work.
   - Subtasks:
     - Draft OpenAPI endpoints and schemas (see `spec.md`).
     - Define discovery file format and write semantics.
     - Provide example client snippets (JS, Python).
   - Acceptance: `openapi.yaml` or `spec.md` exists + minimal example client and task marked complete.
   - Risk: Breaking change — minimize surface area.

2. Implement Backend API Endpoints (not-started)
   - Rationale: Provide server-side behavior for UI and plugins.
   - Subtasks:
     - FastAPI skeleton at `agent/control_api.py` with dynamic port selection and discovery-file writer.
     - Implement `/status`, `/models`, `/plugins`, `/task-history`, `/actions` endpoints.
     - Implement `/ws/events` WebSocket endpoint producing test events.
   - Acceptance: Endpoints respond with mocked data and WS emits sample messages; unit tests cover basic behavior.

3. Scaffold Frontend (Tauri) (not-started)
   - Rationale: Quick SPA to iterate on UX; Tauri packaging later.
   - Subtasks:
     - Create Vite + React skeleton with side-nav and routes: Dashboard, Logs, Models, Plugins, Tasks, Settings.
     - Implement port-discovery client that reads `control_api_port.json` and connects to `/ws/events`.
     - Add Status card, Logs tail component, Plugins list component (mocked data).
   - Acceptance: SPA connects to backend (or mocked endpoint) and displays status/logs/plugins.

4. Add Authentication & Permissions (not-started)
   - Rationale: Protect stateful endpoints and plugin install operations.
   - Subtasks:
     - Auth scheme (local token + OS-integrated fallback).
     - Permission checks for plugin install/uninstall and control actions.
   - Acceptance: Admin-only endpoints require token; UI prompts for auth flow.

5. Design Plugin API & SDK (not-started)
   - Rationale: Define plugin manifest, capabilities, and runtime contract.
   - Subtasks:
     - Plugin manifest spec (id, name, version, entrypoint, requestedCapabilities).
     - JSON-RPC schema for common calls (invoke, healthcheck, ping).
     - Example plugin template (Python) and SDK helpers.
   - Acceptance: `spec.md` includes manifest schema and example plugin.

6. Implement Plugin Loader & Registry (not-started)
   - Rationale: Runtime loader to enumerate, start, stop plugins safely.
   - Subtasks:
     - Plugin registry endpoints (`/plugins`, `/plugins/install`, `/plugins/{id}/action`).
     - Subprocess supervisor with timeout/kill.
   - Acceptance: Install a local example plugin and call a test RPC.

7. Plugin Registry UX (not-started)
   - Rationale: UI for listing, installing, granting capabilities, enabling/disabling plugins.
   - Acceptance: UI shows manifest, capability list, and install confirmation dialog.

8. Task History & Replay (not-started)
   - Rationale: Historic tasks, replay with re-synthesis.
   - Acceptance: Task list with metadata and a `replay` button that triggers backend replay (mocked OK).

9. Notifications & Alerts (not-started)
   - Rationale: Surface important events to user.
   - Acceptance: Toast stack works and receives events from `/ws/events`.

10. Tests, CI & E2E (not-started)
    - Rationale: Ensure regressions are caught early.
    - Acceptance: Basic unit tests for backend endpoints and Vitest for main UI components.

11. Docs, Examples & Release (not-started)
    - Rationale: Make it easy for contributors and users.
    - Acceptance: README with dev steps, example plugin, and release notes.

Notes
-----

The above tasks map directly to the workspace TODO list and are ordered by dependency and business value. Implement tasks sequentially where possible (1 → 2 → 3 etc.).
