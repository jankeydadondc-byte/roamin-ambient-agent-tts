# Spec — Control API (initial outline)

This file captures the minimal API surface for MVP and the WS event contract.

Discovery file
--------------

- Path (recommended): `%APP_DOCS%/.loom/control_api_port.json`
- Format (JSON):

```json
{
  "port": 8765,
  "pid": 12345,
  "started_at": "2026-04-04T12:00:00Z",
  "version": "0.1.0"
}
```

- Write semantics: atomic write (write temp → rename) and restrictive ACL.

REST Endpoints (MVP)
---------------------

GET /status

- 200: {"status":"ok","uptime":12345,"version":"0.1.0","models":[..]}

GET /models

- 200: {"models": [{"id":"qwen3","name":"Qwen3", "status":"loaded"}]}

GET /plugins

- 200: {"plugins": [{"id":"pkg.example","name":"Example","enabled":true,"manifest":{...}}]}

POST /plugins/install

- body: {"source":"file|url","value":"/path/to/zip or https://..."}
- 202: {"task_id":"install-123"}

DELETE /plugins/{plugin_id}

- 200: {"result":"ok"}

GET /task-history

- 200: {"tasks": [{"id":"t1","type":"run","status":"completed","started_at":"..."}]}

POST /actions/{action}

- actions: start | stop | restart
- 200: {"result":"accepted","action":"start"}

WebSocket: /ws/events
---------------------

- Connect to receive a stream of events. Server messages are JSON objects with `type` and `data` fields.

Event types (initial):

- `log_line`: {"source":"agent","line":"...","level":"info"}
- `status_update`: {"uptime":1234,"state":"idle"}
- `task_update`: {"task_id":"t1","status":"running","progress":0.5}
- `plugin_event`: {"plugin_id":"pkg.example","event":"started"}

Plugin manifest schema (minimal)
---------------------------------

- `id` (string), `name` (string), `version` (string), `entrypoint` (string), `requestedCapabilities` (array of strings), `description` (string)

Example manifest:

```json
{
  "id": "pkg.example",
  "name": "Example Plugin",
  "version": "0.1.0",
  "entrypoint": "run.py",
  "requestedCapabilities": ["filesystem","network"],
  "description": "Demo plugin"
}
```

Notes & constraints
-------------------

- Plugin installs must present the manifest to the user with requested capabilities before activation.
- Backend should validate manifest fields and sandbox runtime (minimal at MVP: subprocess with cwd=plugin_dir; later: OS-level sandboxing).
- All mutating endpoints require auth and CSRF protections where applicable.

Acceptance criteria (MVP)
-------------------------

- Control API discovery file is written atomically and readable by local clients.
- `GET /status`, `GET /models`, `GET /plugins` return correct JSON and HTTP 200.
- `POST /plugins/install` schedules an install and returns 202 with `task_id`.
- `POST /plugins/{plugin_id}/action` accepts `enable`/`disable` and broadcasts a `plugin_event` over `/ws/events`.
- WebSocket `/ws/events` reliably broadcasts `log_line`, `task_update`, and `plugin_event` messages during normal operation.
- SPA can install a plugin, list it, enable/disable it, and receive plugin events via WS.

Security & sandboxing (proposal)
--------------------------------

- MVP: Run plugins as subprocesses under a dedicated `plugins/` directory with file-permission restrictions. Limit PATH and use minimal env.
- Require explicit user confirmation UI for requested capabilities (`requestedCapabilities`) before the plugin is activated.
- Future: integrate OS-level sandboxing (AppContainer, Firejail, seccomp) or container-based runtime for untrusted plugins.
- All control endpoints require the `x-roamin-api-key` header when `ROAMIN_CONTROL_API_KEY` is set; document rotation and storage guidance.

API payload examples
--------------------

Install request body (file source):

```json
{ "id": "pkg.example", "name": "Example Plugin", "manifest": {"id":"pkg.example","name":"Example","entrypoint":"run.py"} }
```

Plugin action request body (enable/disable):

```json
{ "action": "enable" }
```

Task record example (task-history):

```json
{ "id": "install-1612345678900", "type": "install", "status": "completed", "timestamp": "2026-04-05T12:00:00Z" }
```

Next steps
----------

- Add acceptance-test vectors and example curl commands to validate the API surface.
- Define the plugin supervisor contract (per-plugin lifecycle API, restart semantics) and update control API to expose a per-plugin status endpoint in a follow-up change.
- Map spec tasks into issues and attach owners and test vectors.
