# Tasks — UX & Plugins Control Panel (prioritized)

Priority order (most to least important)

1. Define Control API Spec (COMPLETED)
   - Rationale: API contract is required before backend/frontend work.
   - Subtasks:
     - Draft OpenAPI endpoints and schemas (see `openapi.yaml`).
     - Define discovery file format and write semantics (in `spec.md`).
     - Provide example client snippets (JS, Python) -- `example_client.js`, `example_client.py`.
   - Acceptance: `openapi.yaml` or `spec.md` exists + minimal example client and task marked complete.
   - Risk: Breaking change -- minimize surface area.

2. Implement Backend API Endpoints (COMPLETED)
   - Rationale: Provide server-side behavior for UI and plugins.
   - Subtasks:
     - FastAPI skeleton at `agent/control_api.py` with dynamic port selection and discovery-file writer.
     - Implement `/status`, `/models`, `/plugins`, `/task-history`, `/actions` endpoints.
     - Implement `/ws/events` WebSocket endpoint producing test events.
     - BONUS: `/health`, `/audit-log`, `/pending-approvals`, `/approve`, `/deny`, `/plugins/validate` endpoints.
     - `/models` wired to real ModelRouter (live model list from model_config.json).
     - `/plugins/{id}/action` supports enable, disable, and restart.
     - Fixed deprecation warnings (datetime.utcnow to datetime.now(UTC), on_event to lifespan).
   - Acceptance: Endpoints respond with mocked data and WS emits sample messages; unit tests cover basic behavior.
   - Tests: 3 passing (tests/test_control_api.py).

3. Scaffold Frontend (Tauri) (COMPLETED)
   - Rationale: Quick SPA to iterate on UX; Tauri packaging later.
   - Subtasks:
     - Vite + React skeleton at `ui/control-panel/` with side-nav (Sidebar.jsx) and sections: Models, Plugins, Supervisor, Install, Logs, Tasks.
     - Port-discovery API client (`src/apiClient.js`) connects to backend + WebSocket with auto-reconnect/backoff.
     - Status header (Header.jsx), Live Events log, Plugin list/detail/actions, Task history, Model selector.
   - Acceptance: SPA connects to backend and displays status/logs/plugins.

4. Add Authentication & Permissions (COMPLETED)
   - Rationale: Protect stateful endpoints and plugin install operations.
   - Subtasks:
     - API key middleware (`x-roamin-api-key` header via `ROAMIN_CONTROL_API_KEY` env var).
     - WebSocket auth (header or query param).
     - `setApiKey()` in apiClient.js for frontend auth wiring.
   - Acceptance: Admin-only endpoints require token; UI prompts for auth flow.

5. Design Plugin API & SDK (COMPLETED)
   - Rationale: Define plugin manifest, capabilities, and runtime contract.
   - Subtasks:
     - Plugin manifest spec in `spec.md` (id, name, version, entrypoint, requestedCapabilities).
     - RoaminPlugin protocol in `agent/plugins/__init__.py` (name, on_load, on_unload).
     - Example plugin template: `agent/plugins/example_ping.py`.
     - CapabilityHints.jsx for frontend capability display.
   - Acceptance: `spec.md` includes manifest schema and example plugin.

6. Implement Plugin Loader & Registry (COMPLETED)
   - Rationale: Runtime loader to enumerate, start, stop plugins safely.
   - Subtasks:
     - Plugin loader in `agent/plugins/__init__.py` (discover, import, validate, on_load).
     - Plugin registry endpoints in control_api.py (`/plugins`, `/plugins/install`, `/plugins/{id}/action`).
     - Supervisor.jsx component for plugin process management.
   - Acceptance: Install a local example plugin and call a test RPC.

7. Plugin Registry UX (COMPLETED)
   - Rationale: UI for listing, installing, granting capabilities, enabling/disabling plugins.
   - Subtasks:
     - PluginList.jsx, PluginDetail.jsx, PluginActions.jsx, CapabilityHints.jsx components.
     - Install confirmation flow with manifest display and capability review.
   - Acceptance: UI shows manifest, capability list, and install confirmation dialog.

8. Task History & Replay (COMPLETED)
   - Rationale: Historic tasks, replay with re-synthesis.
   - Subtasks:
     - TaskHistory.jsx component with filtering and live `task_update` handling.
     - `/task-history` endpoint reads from SQLite `task_runs` table with status/since/keyword filters.
     - `/task-history/{task_id}/steps` endpoint for step-level detail.
   - Acceptance: Task list with metadata displayed; step-level detail available via API.

9. Notifications & Alerts (COMPLETED)
   - Rationale: Surface important events to user.
   - Subtasks:
     - Toast.jsx notification component.
     - WebSocket event stream (`/ws/events`) with `log_line`, `status_update`, `task_update`, `plugin_event` types.
     - HITL approval toasts via `/approve` and `/deny` endpoints.
   - Acceptance: Toast stack works and receives events from `/ws/events`.

10. Tests, CI & E2E (COMPLETED)
    - Rationale: Ensure regressions are caught early.
    - Subtasks:
      - Backend unit tests: 3 tests in `tests/test_control_api.py` (status, install+list, enable/disable).
      - Unit test suite: 37+ tests across `tests/unit/` (Priority 9 testing framework).
      - Playwright E2E deferred (personal tool, not blocking).
    - Acceptance: Basic unit tests for backend endpoints pass.

11. Docs, Examples & Release (COMPLETED)
    - Rationale: Make it easy for contributors and users.
    - Subtasks:
      - `openspec/changes/ux-plugins-control-panel/spec.md` -- comprehensive API spec.
      - `openspec/changes/ux-plugins-control-panel/openapi.yaml` -- formal OpenAPI 3.0 spec.
      - Example clients: `example_client.py` (async Python), `example_client.js` (JS/Node).
      - `ui/control-panel/README.md` exists.
      - `agent/plugins/example_ping.py` as plugin template.
    - Acceptance: Spec, OpenAPI, example clients, and example plugin all present.

Notes
-----

All 11 tasks are now COMPLETED. This proposal can be archived.
The above tasks map directly to the workspace TODO list and were ordered by dependency and business value.
