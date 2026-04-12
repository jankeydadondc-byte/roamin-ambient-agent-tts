# Spec: Control Panel — API & WS

This file captures the API surface and WebSocket event shapes used by the Control Panel SPA for the `ux-plugins-control-panel-next` OpenSpec change.

## REST API Endpoints (summary)

- `GET /status`
  - Response: { status: "ok", uptime: number, version: string, models: [ { id, name, status } ] }

- `GET /models`
  - Response: array of model metadata

- `GET /plugins`
  - Response: array of plugin metadata
    - plugin metadata: { id, name, version, enabled, manifest: {description, requestedCapabilities, ...}, installed_at }

- `POST /plugins/validate`
  - Request: { manifest: object }
  - Response: { valid: boolean, manifest: object, warnings?: [], errors?: [] }
  - Purpose: client shows manifest and requestedCapabilities; user must explicitly Accept.

- `POST /plugins/install`
  - Request: { manifest: object }
  - Response: 202 Accepted, { task_id: string }
  - Purpose: install is performed asynchronously by a task worker; control API will emit task updates.

- `POST /plugins/{id}/action`
  - Request: { action: "enable" | "disable" | "restart" | "uninstall" }
  - Response: 202 Accepted or immediate 200 for quick ops

- `GET /task-history`
  - Response: array of task records
  - Task record: { id, type, status, started_at, finished_at?, progress?, meta?: {} }

## WebSocket: `/ws/events`

Clients connect to receive real-time events. If an API key is set, client should include it in the WS handshake (e.g. a `x-roamin-api-key` header or query param if the server supports it).

Event envelope:
{ "type": "<event_type>", "payload": { ... }, "ts": 1670000000 }

Known event types:

- `log_line` — payload: { plugin_id?, line: string, level?: "info"|"warn"|"error" }
- `task_update` — payload: { task_id, status, progress?, meta?: {} }
- `plugin_event` — payload: { plugin_id, event: "installed"|"enabled"|"disabled"|"failed", details?: {} }

WS behavior:

- Clients must be resilient: implement reconnect/backoff with jitter, handle duplicate events idempotently, and re-synchronize by fetching `GET /task-history` on reconnect.
- Status indicators: the SPA exposes `connecting`, `open`, `closed` states for UX.

## Security & API Key

- REST requests should include header: `x-roamin-api-key: <token>` when set.
- WebSocket connections should include the API key if the server requires it.
- The SPA stores the API key in `localStorage` for developer convenience; for production, consider a secure store.

## Acceptance Criteria (spec-level)

- The manifest confirmation flow shows `requestedCapabilities` and requires explicit user acceptance before calling `/plugins/install`.
- Plugin installs return a `task_id` and the task appears in `/task-history` within 5s and then emits `task_update` messages until completion.
- WebSocket reconnection recovers event stream and the SPA resynchronizes by refetching `GET /task-history` on open.
- API key header is applied to REST and WS requests when set.

## Versioning & Backwards Compatibility

- Additive changes only: new optional fields permitted; clients should tolerate unknown fields.

## Open Questions

- Should the server provide server-side pagination for `/task-history`? (Recommended for large deployments.)
- Preferred mechanism for WS API key transport: header vs query string. Header is preferred but not all WS clients allow custom headers.

---

This spec file should be kept in sync with `agent/control_api.py` and `ui/control-panel/src/apiClient.js`.
