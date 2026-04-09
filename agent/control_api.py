"""FastAPI Control API skeleton for Roamin (MVP).

Provides minimal endpoints and a WebSocket event stream suitable for local UI development
and integration with the SPA prototype. This module is intentionally small and mock-backed
so it can be iterated on; production hardening (auth, ACLs, sandboxing) comes later.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from agent.core import paths, ports
from agent.core.secrets import get_secret

logger = logging.getLogger(__name__)

app = FastAPI(title="Roamin Control API (dev)")

# Allow local dev browser connections by default for the SPA prototype
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _api_key_middleware(request: Request, call_next):
    """Optional API-key middleware: if `ROAMIN_CONTROL_API_KEY` is set, require
    header `x-roamin-api-key` to match the value. This keeps tests and local
    development working when the env var is unset.
    """
    # Use centralized secrets loader for API key
    key = get_secret("ROAMIN_CONTROL_API_KEY")
    if key:
        provided = request.headers.get("x-roamin-api-key")
        if provided != key:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


def _find_free_port_in_range() -> int:
    """Return first unused port in configured range, or default port if none free."""
    for p in ports.CONTROL_API_PORT_RANGE:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", p))
        except OSError:
            # bind failed → port in use
            continue
        else:
            return p
    return ports.CONTROL_API_DEFAULT_PORT


def _write_discovery_file(port: int) -> Path:
    """Write an atomic discovery record under <project_root>/.loom/control_api_port.json.

    The file is written atomically (temp -> replace). Returns the path written.
    """
    try:
        project_root = paths.get_project_root()
    except Exception:
        project_root = Path.cwd()

    loom_dir = project_root / ".loom"
    loom_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "port": int(port),
        "pid": os.getpid(),
        "started_at": datetime.utcnow().isoformat() + "Z",
        "version": "0.1.0",
    }

    tmp_fd, tmp_path = tempfile.mkstemp(prefix="control_api_port", dir=str(loom_dir))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(record, f)
            f.flush()
            os.fsync(f.fileno())

        dest = loom_dir / "control_api_port.json"
        os.replace(tmp_path, dest)
        return dest
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.on_event("startup")
async def _startup_event() -> None:
    """Initialise in-memory state and start background broadcaster."""
    # In-memory 'database' for prototype
    app.state.models = [{"id": "dummy-model", "name": "Dummy", "status": "idle"}]
    app.state.plugins: list[dict[str, Any]] = []
    app.state.tasks: list[dict[str, Any]] = []
    app.state.websockets: set[WebSocket] = set()

    # Determine a preferred port and write discovery file so local UIs can find us.
    port = int(os.environ.get("ROAMIN_CONTROL_API_PORT") or _find_free_port_in_range())
    # Persist discovery info for local clients (atomic)
    try:
        _write_discovery_file(port)
    except Exception:
        # Non-fatal for prototype
        pass

    # Start background task that emits sample events every second
    async def _broadcaster() -> None:
        counter = 0
        while True:
            event = {
                "type": "log_line",
                "data": {"source": "control_api", "line": f"heartbeat {counter}", "level": "info"},
            }
            await _broadcast(event)
            counter += 1
            await asyncio.sleep(1)

    asyncio.create_task(_broadcaster())


async def _broadcast(event: dict[str, Any]) -> None:
    """Send `event` to all connected websockets; prune disconnected sockets."""
    dead: list[WebSocket] = []
    for ws in list(app.state.websockets):
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)

    for ws in dead:
        try:
            app.state.websockets.remove(ws)
        except KeyError:
            pass


@app.websocket("/ws/events")
async def websocket_events(ws: WebSocket) -> None:
    # If API key is configured, require it for websocket connections as well.
    # Accept API key from either HTTP header (preferred) or query parameter (for WebSocket compatibility)
    key = get_secret("ROAMIN_CONTROL_API_KEY")
    if key:
        # Try header first, then query param (for WebSocket compatibility)
        provided = ws.headers.get("x-roamin-api-key") or ws.query_params.get("api_key")

        if os.environ.get("ROAMIN_DEBUG"):
            logger.info(
                f"WebSocket auth: header={ws.headers.get('x-roamin-api-key')}, query={ws.query_params.get('api_key')}"
            )

        if provided != key:
            if os.environ.get("ROAMIN_DEBUG"):
                logger.warning(f"WebSocket auth failed: expected {key}, got {provided}")
            await ws.close(code=1008)
            return

    await ws.accept()
    app.state.websockets.add(ws)
    try:
        while True:
            # Keep connection open; accept pings from client to avoid timeouts
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                # no-op; continue to keep socket alive
                await asyncio.sleep(0.1)
    finally:
        try:
            app.state.websockets.remove(ws)
        except Exception:
            pass


@app.get("/status")
async def get_status() -> dict[str, Any]:
    return {
        "status": "ok",
        "uptime": int(time.time()),
        "version": "0.1.0",
        "models": app.state.models,
    }


@app.get("/models")
async def list_models() -> dict[str, Any]:
    return {"models": app.state.models}


@app.get("/plugins")
async def list_plugins() -> dict[str, Any]:
    return {"plugins": app.state.plugins}


@app.get("/plugins/{plugin_id}")
async def get_plugin(plugin_id: str) -> dict[str, Any]:
    for p in app.state.plugins:
        if p.get("id") == plugin_id:
            return p
    raise HTTPException(status_code=404, detail="plugin not found")


@app.post("/plugins/{plugin_id}/action")
async def plugin_action(plugin_id: str, body: dict[str, Any]) -> dict[str, Any]:
    action = body.get("action")
    if action not in ("enable", "disable"):
        raise HTTPException(status_code=400, detail="unknown action")

    for p in app.state.plugins:
        if p.get("id") == plugin_id:
            p["enabled"] = True if action == "enable" else False
            app.state.tasks.append(
                {
                    "id": f"plugin-action-{int(time.time()*1000)}",
                    "type": action,
                    "plugin": plugin_id,
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            )
            await _broadcast({"type": "plugin_event", "data": {"plugin_id": plugin_id, "event": action}})
            return {"result": "ok", "action": action}

    raise HTTPException(status_code=404, detail="plugin not found")


@app.post("/plugins/validate")
async def validate_plugin_manifest(body: dict[str, Any]) -> dict[str, Any]:
    # Minimal validation for prototype
    required = {"id", "name", "entrypoint"}
    raw = body.get("manifest")
    manifest: dict[str, Any] = raw if isinstance(raw, dict) else body
    missing = [k for k in required if k not in manifest]
    return {"valid": len(missing) == 0, "missing": missing}


async def _simulate_install(payload: dict[str, Any], task_id: str) -> None:
    # Simulate a plugin install, then broadcast plugin_event
    await asyncio.sleep(1)
    plugin = {
        "id": payload.get("id") or f"pkg.{int(time.time())}",
        "name": payload.get("name") or "Unknown",
        "enabled": True,
        "manifest": payload.get("manifest") or {},
    }
    app.state.plugins.append(plugin)
    app.state.tasks.append(
        {"id": task_id, "type": "install", "status": "completed", "timestamp": datetime.utcnow().isoformat() + "Z"}
    )
    await _broadcast({"type": "plugin_event", "data": {"plugin_id": plugin["id"], "event": "installed"}})


@app.post("/plugins/install")
async def install_plugin(body: dict[str, Any]) -> JSONResponse:
    task_id = f"install-{int(time.time() * 1000)}"
    # Schedule the install coroutine on the running event loop
    try:
        asyncio.create_task(_simulate_install(body, task_id))
    except RuntimeError:
        # If no running loop is available, run synchronously in a new loop
        asyncio.run(_simulate_install(body, task_id))
    return JSONResponse(status_code=202, content={"task_id": task_id})


@app.delete("/plugins/{plugin_id}")
async def uninstall_plugin(plugin_id: str) -> dict[str, Any]:
    before = len(app.state.plugins)
    app.state.plugins = [p for p in app.state.plugins if p.get("id") != plugin_id]
    after = len(app.state.plugins)
    if before == after:
        raise HTTPException(status_code=404, detail="plugin not found")
    await _broadcast({"type": "plugin_event", "data": {"plugin_id": plugin_id, "event": "uninstalled"}})
    return {"result": "ok"}


@app.get("/task-history")
async def task_history(
    since: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    """Return persistent task history from SQLite (with optional filters).

    Falls back to in-memory tasks if the MemoryStore is unavailable.
    """
    try:
        from agent.core.memory import MemoryManager

        mm = MemoryManager()
        runs = mm.query_tasks(limit=50, status=status, since=since, keyword=q)
        return {"tasks": runs}
    except Exception:
        # Fallback to in-memory plugin/action tasks
        return {"tasks": app.state.tasks}


@app.get("/task-history/{task_id}/steps")
async def task_steps(task_id: int) -> dict[str, Any]:
    """Return steps for a specific task run."""
    try:
        from agent.core.memory.memory_store import MemoryStore

        store = MemoryStore()
        steps = store.get_task_steps(task_id)
        return {"steps": steps}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


_CLOSE_HTML = """<html><body style="font-family:sans-serif;padding:2em">
<p>{msg}</p><script>setTimeout(()=>window.close(),1500)</script></body></html>"""


@app.get("/pending-approvals")
async def list_pending_approvals() -> dict[str, Any]:
    """Return all steps currently awaiting user approval."""
    try:
        from agent.core.memory.memory_store import MemoryStore

        store = MemoryStore()
        return {"approvals": store.get_pending_approvals()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/approve/{approval_id}", response_class=HTMLResponse)
async def approve_step(approval_id: int) -> HTMLResponse:
    """Execute an approved blocked step and mark it resolved."""
    try:
        from agent.core.memory.memory_store import MemoryStore
        from agent.core.screen_observer import _notify_windows
        from agent.core.tool_registry import ToolRegistry

        store = MemoryStore()
        record = store.get_pending_approval(approval_id)
        if record is None:
            return HTMLResponse(_CLOSE_HTML.format(msg="Approval not found."), status_code=404)
        if record["status"] != "pending":
            return HTMLResponse(_CLOSE_HTML.format(msg=f"Already {record['status']}."))

        # Execute the step via ToolRegistry
        tool_name = record.get("tool")
        params: dict[str, Any] = {}
        if record.get("params_json"):
            try:
                params = json.loads(record["params_json"])
            except Exception:
                pass

        outcome = ""
        if tool_name:
            registry = ToolRegistry()
            result = registry.execute(tool_name, params)
            outcome = str(result.get("result") or result.get("error", ""))[:200]

        store.resolve_approval(approval_id, "approved")
        await _broadcast({"type": "approval_resolved", "data": {"id": approval_id, "status": "approved"}})
        _notify_windows(f"Approved: {outcome or record['action'][:60]}", title="Roamin — Step Approved")
        return HTMLResponse(_CLOSE_HTML.format(msg=f"Step approved and executed. {outcome}"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/deny/{approval_id}", response_class=HTMLResponse)
async def deny_step(approval_id: int) -> HTMLResponse:
    """Mark a blocked step as denied without executing it."""
    try:
        from agent.core.memory.memory_store import MemoryStore

        store = MemoryStore()
        record = store.get_pending_approval(approval_id)
        if record is None:
            return HTMLResponse(_CLOSE_HTML.format(msg="Approval not found."), status_code=404)
        if record["status"] != "pending":
            return HTMLResponse(_CLOSE_HTML.format(msg=f"Already {record['status']}."))

        store.resolve_approval(approval_id, "denied")
        await _broadcast({"type": "approval_resolved", "data": {"id": approval_id, "status": "denied"}})
        return HTMLResponse(_CLOSE_HTML.format(msg="Step denied."))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/audit-log")
async def get_audit_log(limit: int = 50, tool: str | None = None, since: str | None = None):
    """Query the tool execution audit log (JSONL backend)."""
    from agent.core import audit_log

    entries = audit_log.query(limit=limit, tool_filter=tool, since=since)
    return {"entries": entries, "count": len(entries)}


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Return current CPU/RAM/VRAM usage and throttle status."""
    try:
        from agent.core.resource_monitor import get_throttle_status

        status = get_throttle_status()
    except Exception as exc:
        status = {"error": str(exc)}
    status["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return status


@app.post("/actions/cleanup-tasks")
async def cleanup_tasks(older_than_hours: int = 24) -> dict[str, Any]:
    """Delete completed task_runs older than *older_than_hours* (default 24)."""
    from agent.core.agent_loop import AgentLoop

    loop = AgentLoop()
    return loop._cleanup_completed_tasks(older_than_hours=older_than_hours)


@app.post("/actions/{action}")
async def control_action(action: str) -> dict[str, Any]:
    if action not in ("start", "stop", "restart"):
        raise HTTPException(status_code=400, detail="unknown action")

    task = {
        "id": f"action-{int(time.time()*1000)}",
        "type": action,
        "status": "accepted",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    app.state.tasks.append(task)
    await _broadcast({"type": "task_update", "data": {"task_id": task["id"], "status": "running"}})
    return {"result": "accepted", "action": action}
