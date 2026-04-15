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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from agent.core import paths, ports
from agent.core.secrets import get_secret

logger = logging.getLogger(__name__)

# Eviction limit for in-memory task list — prevents unbounded growth (#88)
_TASK_EVICT_LIMIT = 500


def _append_task(task: dict[str, Any]) -> None:
    """Append a task entry and evict the oldest half when over the limit."""
    app.state.tasks.append(task)
    if len(app.state.tasks) > _TASK_EVICT_LIMIT:
        keep = _TASK_EVICT_LIMIT // 2
        app.state.tasks = app.state.tasks[-keep:]


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Modern lifespan handler replacing deprecated @app.on_event('startup')."""
    await _startup_init(application)
    yield


app = FastAPI(title="Roamin Control API (dev)", lifespan=lifespan)

# Restrict CORS to known local origins — wildcard removed to reduce CSRF surface.
# Tauri WebView origins vary by platform/version:
#   Windows WebView2 (Tauri v2): tauri://localhost  or  https://tauri.localhost
#   Tauri v1 legacy:             tauri://localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Browser control panel (Vite dev server)
        "http://localhost",
        "http://localhost:5173",
        "http://127.0.0.1",
        "http://127.0.0.1:5173",
        # Tauri chat app (roamin-chat) — Tauri v2 / WebView2 origins
        # Windows WebView2 (Tauri v2) uses http://tauri.localhost as the actual
        # browser origin — NOT tauri://localhost or https://tauri.localhost.
        "http://tauri.localhost",
        "http://localhost:1420",
        "tauri://localhost",
        "https://tauri.localhost",
    ],
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
        "started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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


async def _startup_init(application: FastAPI) -> None:
    """Initialise in-memory state and start background broadcaster."""
    application.state.started_at = time.time()

    # Load real model list from ModelRouter (fall back to dummy if unavailable)
    try:
        from agent.core.model_router import ModelRouter

        router = ModelRouter()
        application.state.models = [
            {
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "status": "loaded" if m.get("always_available") else "unloaded",
                "provider": m.get("provider", "unknown"),
                "capabilities": m.get("capabilities", []),
            }
            for m in router.list_models()
        ]
    except Exception:
        application.state.models = [{"id": "dummy-model", "name": "Dummy", "status": "idle"}]

    application.state.plugins: list[dict[str, Any]] = []
    application.state.tasks: list[dict[str, Any]] = []
    application.state.websockets: set[WebSocket] = set()

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
                # Redact key value — never log credential material
                logger.warning(
                    "WebSocket auth failed: expected key len=%d, got=%s",
                    len(key),
                    "***" if provided else "(none)",
                )
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
    uptime = int(time.time() - getattr(app.state, "started_at", time.time()))
    return {
        "status": "ok",
        "uptime": uptime,
        "version": "0.1.0",
        "models": app.state.models,
    }


@app.get("/models")
async def list_models() -> dict[str, Any]:
    return {"models": app.state.models}


@app.post("/models/select")
async def select_model(request: Request) -> dict[str, Any]:
    """Switch the model used for a routing task at runtime.

    Body: ``{"model_id": "some-model-id", "task": "default"}``
    Send ``model_id: ""`` or ``null`` to revert to config default.
    """
    body = await request.json()
    model_id = (body.get("model_id") or "").strip()
    task = (body.get("task") or "default").strip()

    from agent.core.model_router import ModelRouter, clear_task_model, set_task_model

    if not model_id:
        clear_task_model(task)
        return {"status": "ok", "task": task, "model_id": None, "message": f"Reverted '{task}' to config default"}

    router = ModelRouter()
    known = {m["id"] for m in router.list_models()}
    if model_id not in known:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found in config")

    set_task_model(task, model_id)
    model_cfg = router.select(task)

    # Persist: update model_overrides + default_model in settings.local.json
    from agent.core import settings_store

    settings = settings_store.load()
    overrides: dict[str, str] = settings.get("model_overrides", {})
    overrides[task] = model_id
    settings["model_overrides"] = overrides
    if task == "default":
        settings["default_model"] = model_id
    settings_store.save(settings)

    # Best-effort: tell LM Studio to load the model
    lm_id = model_cfg.get("model_id", model_id)
    lm_loaded = False
    try:
        import requests as _requests  # noqa: PLC0415

        resp = _requests.post(
            "http://127.0.0.1:1234/api/v0/models/load",
            json={"identifier": lm_id},
            timeout=5,
        )
        lm_loaded = resp.ok
        if not resp.ok:
            logger.warning("LM Studio load returned %s for model '%s'", resp.status_code, lm_id)
    except Exception as lm_err:
        logger.debug("LM Studio load skipped (not reachable?): %s", lm_err)

    return {
        "status": "ok",
        "task": task,
        "model_id": model_id,
        "model_name": model_cfg.get("name", model_id),
        "lm_loaded": lm_loaded,
    }


@app.post("/models/refresh")
async def refresh_models() -> dict[str, Any]:
    """Query LM Studio for available models and reconcile with config.

    - Marks models not present in LM Studio as status='unavailable'
    - Adds any net-new LM Studio models to the in-memory list
    - Updates app.state.models so GET /models reflects fresh state
    """
    import requests as _requests  # noqa: PLC0415

    try:
        resp = _requests.get("http://127.0.0.1:1234/api/v0/models", timeout=5)
        if not resp.ok:
            return {"refreshed": False, "error": f"LM Studio returned {resp.status_code}", "models": app.state.models}

        lm_models: list[dict[str, Any]] = resp.json().get("data", [])
        lm_ids: set[str] = {m.get("id", "") for m in lm_models}

        # Mark existing models available/unavailable based on LM Studio response
        updated: list[dict[str, Any]] = []
        for m in app.state.models:
            mid = m.get("id", "")
            lm_model_id = m.get("model_id", mid)
            in_lm = any(lm_id in (mid, lm_model_id) for lm_id in lm_ids)
            updated.append({**m, "status": "loaded" if in_lm else "unavailable"})

        # Add net-new models from LM Studio not already in the list
        existing_model_ids = {m.get("model_id", m.get("id", "")) for m in app.state.models}
        for lm in lm_models:
            lm_model_id = lm.get("id", "")
            if lm_model_id not in existing_model_ids:
                updated.append(
                    {
                        "id": lm_model_id,
                        "name": lm.get("id", lm_model_id),
                        "model_id": lm_model_id,
                        "provider": "lmstudio",
                        "status": "loaded",
                        "always_available": False,
                    }
                )

        app.state.models = updated
        logger.info("Model list refreshed: %d models (%d from LM Studio)", len(updated), len(lm_models))
        return {"refreshed": True, "models": updated}

    except Exception as e:
        logger.warning("POST /models/refresh failed: %s", e)
        return {"refreshed": False, "error": str(e), "models": app.state.models}


@app.get("/models/current")
async def current_model_routing() -> dict[str, Any]:
    """Return the active routing table with any runtime overrides flagged."""
    from agent.core.model_router import ModelRouter, get_task_overrides

    router = ModelRouter()
    overrides = get_task_overrides()
    routing: dict[str, Any] = {}
    for task, model_id in router._rules.items():
        override = overrides.get(task)
        routing[task] = {
            "model_id": override or model_id,
            "overridden": override is not None,
        }
    return {"routing": routing, "overrides": overrides}


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
    if action not in ("enable", "disable", "restart"):
        raise HTTPException(status_code=400, detail="unknown action")

    for p in app.state.plugins:
        if p.get("id") == plugin_id:
            if action in ("enable", "disable"):
                p["enabled"] = action == "enable"
            # restart: toggle off then on (status remains enabled)
            _append_task(
                {
                    "id": f"plugin-action-{int(time.time()*1000)}",
                    "type": action,
                    "plugin": plugin_id,
                    "status": "completed",
                    "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
    _append_task(
        {
            "id": task_id,
            "type": "install",
            "status": "completed",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
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
    page: int = 1,
    per_page: int = 20,
    since: str | None = None,
    status: str | None = None,
    task_type: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    """Return persistent task history from SQLite with server-side pagination.

    Query params:
      page       — 1-based page number (default 1)
      per_page   — results per page (default 20, max 100)
      status     — filter by status (pending|running|completed|failed)
      task_type  — filter by task_type column
      since      — ISO-8601 datetime lower bound on started_at
      q          — keyword search across all fields

    Falls back to in-memory tasks if the MemoryStore is unavailable.
    """
    per_page = min(max(1, per_page), 100)
    page = max(1, page)
    try:
        from agent.core.memory import MemoryManager

        mm = MemoryManager()
        result = mm.query_tasks(
            limit=per_page,
            page=page,
            status=status,
            since=since,
            task_type=task_type,
            keyword=q,
        )
        return result
    except Exception:
        # Fallback to in-memory plugin/action tasks (no pagination)
        tasks = app.state.tasks
        return {
            "tasks": tasks,
            "total": len(tasks),
            "page": 1,
            "per_page": len(tasks),
            "pages": 1,
        }


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


@app.post("/approve/{approval_id}", response_class=HTMLResponse)
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


@app.post("/deny/{approval_id}", response_class=HTMLResponse)
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
    status["timestamp"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    _append_task(task)
    await _broadcast({"type": "task_update", "data": {"task_id": task["id"], "status": "running"}})
    return {"result": "accepted", "action": action}


# ---------------------------------------------------------------------------
# Chat & Conversation Continuity (Priority 11.6)
# ---------------------------------------------------------------------------


@app.get("/chat/history")
async def chat_history(
    session_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return recent conversation exchanges from the session transcript.

    Query params:
        session_id: filter by session (default: current session)
        limit: max results (default 50)
        offset: pagination offset (default 0)
    """
    try:
        from agent.core.voice.session import get_session

        session = get_session()
        history = session.get_history(session_id=session_id, limit=limit, offset=offset)
        return {
            "session_id": session_id or session.session_id,
            "exchanges": history,
            "count": len(history),
        }
    except Exception as e:
        logger.warning("GET /chat/history failed: %s", e)
        return {"session_id": None, "exchanges": [], "count": 0}


@app.post("/chat")
async def chat_send(request: Request) -> dict[str, Any]:
    """Accept a text message, run through the unified Roamin pipeline, return response.

    Delegates all processing to ``chat_engine.process_message()`` which handles
    fact extraction, memory recall, MemPalace, AgentLoop tools, and ModelRouter
    reply generation — the same pipeline used by the voice wake listener.

    Body JSON: { "message": "...", "include_screen": false }
    """
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    include_screen = body.get("include_screen", False)

    try:
        from agent.core.chat_engine import process_message
        from agent.core.voice.session import get_session

        session = get_session()

        # Add user message to session transcript
        session.add("user", message)

        # Run the full pipeline (blocking — offload to thread for async)
        # return_reasoning=True captures <think> blocks before they are stripped
        raw = await asyncio.to_thread(
            process_message,
            message,
            session=session,
            include_screen=include_screen,
            mode="chat",
            return_reasoning=True,
        )
        # return_reasoning=True always returns a dict — cast to satisfy mypy
        result: dict[str, Any] = raw if isinstance(raw, dict) else {"reply": raw, "reasoning": None}
        reply = result["reply"]
        reasoning = result.get("reasoning")

        await _broadcast({"type": "chat_response", "data": {"message": reply}})

        return {
            "response": reply,
            "reasoning": reasoning,
            "session_id": session.session_id,
        }
    except Exception as e:
        logger.error("POST /chat failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/reset")
async def chat_reset() -> dict[str, Any]:
    """Reset the conversation session (start fresh)."""
    try:
        from agent.core.voice.session import get_session

        session = get_session()
        new_id = session.reset(reason="api")
        return {"session_id": new_id, "status": "reset"}
    except Exception as e:
        logger.warning("POST /chat/reset failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/pending")
async def chat_pending() -> dict[str, Any]:
    """Return pending proactive notifications (messages Roamin wanted to say)."""
    try:
        # ProactiveEngine is instantiated in run_wake_listener — no shared
        # instance is accessible here. Return empty; the Tauri chat overlay
        # will poll this endpoint once wiring is added.
        return {"messages": [], "count": 0}
    except Exception:
        return {"messages": [], "count": 0}


@app.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    """List all stored chat sessions with metadata for the session history sidebar."""
    try:
        import sqlite3

        from agent.core.paths import get_project_root
        from agent.core.voice.session import get_session

        db_path = get_project_root() / "agent" / "core" / "memory" / "roamin_memory.db"
        if not db_path.exists():
            return {"sessions": [], "current_session_id": None}

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                session_id,
                MIN(timestamp) AS started_at,
                MAX(timestamp) AS last_at,
                COUNT(*) AS message_count,
                (
                    SELECT content FROM conversation_history c2
                    WHERE c2.session_id = c.session_id
                    ORDER BY timestamp ASC LIMIT 1
                ) AS first_message
            FROM conversation_history c
            GROUP BY session_id
            ORDER BY last_at DESC
            LIMIT 100
            """
        )
        rows = cursor.fetchall()
        conn.close()

        sessions = [
            {
                "session_id": r["session_id"],
                "started_at": r["started_at"],
                "last_at": r["last_at"],
                "message_count": r["message_count"],
                "first_message": (r["first_message"] or "")[:120],
            }
            for r in rows
        ]

        current = get_session()
        return {"sessions": sessions, "current_session_id": current.session_id}
    except Exception as e:
        logger.warning("GET /sessions failed: %s", e)
        return {"sessions": [], "current_session_id": None}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, Any]:
    """Delete all messages for a session from the conversation history database."""
    try:
        import sqlite3

        db_path = paths.get_project_root() / "agent" / "core" / "memory" / "roamin_memory.db"
        if not db_path.exists():
            raise HTTPException(status_code=404, detail="Database not found")

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversation_history WHERE session_id = ?", (session_id,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted == 0:
            return {"deleted": 0, "status": "not_found"}

        logger.info("Deleted session %s (%d messages)", session_id, deleted)
        return {"deleted": deleted, "session_id": session_id, "status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("DELETE /sessions/%s failed: %s", session_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/system-prompt")
async def get_system_prompt() -> dict[str, Any]:
    """Return the current system prompt text from disk."""
    prompts: dict[str, str] = {}
    # Primary system prompt (personality)
    primary = paths.get_project_root() / "roamin ambient agent system prompt.txt"
    if primary.exists():
        prompts["primary"] = primary.read_text(encoding="utf-8")
    # Sidecar prompt (persona/context)
    sidecar = paths.get_project_root() / "agent" / "core" / "system_prompt.txt"
    if sidecar.exists():
        prompts["sidecar"] = sidecar.read_text(encoding="utf-8")
    return {"prompts": prompts}


@app.get("/tools")
async def get_tools() -> dict[str, Any]:
    """List all registered agent tools with name, description, risk, and enabled state."""
    try:
        from agent.core import settings_store
        from agent.core.tool_registry import ToolRegistry

        registry = ToolRegistry()
        tool_states: dict[str, bool] = settings_store.get("tool_states", {})
        tools = [
            {
                "name": name,
                "description": meta.get("description", ""),
                "risk": meta.get("risk", "low"),
                "enabled": tool_states.get(name, True),  # default enabled
            }
            for name, meta in registry._tools.items()
        ]
        return {"tools": sorted(tools, key=lambda t: t["name"])}
    except Exception as e:
        logger.warning("GET /tools failed: %s", e)
        return {"tools": []}


@app.post("/tools/{tool_name}/toggle")
async def toggle_tool(tool_name: str, request: Request) -> dict[str, Any]:
    """Enable or disable a tool by name. Persisted to settings.local.json."""
    try:
        from agent.core import settings_store
        from agent.core.tool_registry import ToolRegistry

        body = await request.json()
        enabled: bool = bool(body.get("enabled", True))

        registry = ToolRegistry()
        if tool_name not in registry._tools:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

        settings = settings_store.load()
        tool_states: dict[str, bool] = settings.get("tool_states", {})
        tool_states[tool_name] = enabled
        settings["tool_states"] = tool_states
        settings_store.save(settings)

        logger.info("Tool '%s' %s", tool_name, "enabled" if enabled else "disabled")
        return {"tool": tool_name, "enabled": enabled, "status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("POST /tools/%s/toggle failed: %s", tool_name, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Settings (Priority 11.3b)
# ---------------------------------------------------------------------------


@app.get("/settings")
async def get_settings() -> dict[str, Any]:
    """Return current Roamin settings — merged from settings.local.json + env-var defaults."""
    from agent.core import settings_store

    persisted = settings_store.load()
    return {
        "volume": persisted.get("volume", 1.0),
        "screenshots_enabled": persisted.get("screenshots_enabled", True),
        "always_on_top": persisted.get("always_on_top", False),
        "default_model": persisted.get("default_model", ""),
        "proactive_enabled": True,
        "observation_interval": int(os.environ.get("ROAMIN_OBS_INTERVAL", "30")),
        "session_timeout_min": int(os.environ.get("ROAMIN_SESSION_TIMEOUT_MIN", "30")),
        "wake_threshold": float(os.environ.get("ROAMIN_WAKE_THRESHOLD", "0.5")),
    }


@app.post("/settings/volume")
async def set_volume(request: Request) -> dict[str, Any]:
    """Set TTS volume (0.0 to 1.0). Persisted to settings.local.json."""
    from agent.core import settings_store

    body = await request.json()
    volume = float(body.get("volume", 1.0))
    if not (0.0 <= volume <= 1.0):
        raise HTTPException(status_code=400, detail="volume must be 0.0-1.0")
    settings_store.set_value("volume", volume)
    return {"volume": volume, "status": "ok"}


@app.post("/settings/screenshots")
async def set_screenshots(request: Request) -> dict[str, Any]:
    """Enable or disable screenshot observation. Persisted to settings.local.json."""
    from agent.core import settings_store

    body = await request.json()
    enabled = bool(body.get("enabled", True))
    settings_store.set_value("screenshots_enabled", enabled)
    return {"screenshots_enabled": enabled, "status": "ok"}


@app.post("/settings/update")
async def update_settings(request: Request) -> dict[str, Any]:
    """Bulk-update any settings keys. Persisted to settings.local.json."""
    from agent.core import settings_store

    body = await request.json()
    # Whitelist of allowed keys to avoid arbitrary data injection
    allowed = {"volume", "screenshots_enabled", "always_on_top", "default_model"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid settings keys provided")
    settings_store.update(updates)
    return {"updated": list(updates.keys()), "status": "ok"}


# ---------------------------------------------------------------------------
# Agent Definitions (§2.5)
# ---------------------------------------------------------------------------


def _agents_dir() -> Path:
    return paths.get_project_root() / "agents"


@app.get("/agents")
async def list_agents() -> dict[str, Any]:
    """List all agent definition YAML files from the agents/ folder."""
    try:
        import yaml as _yaml  # pyyaml — available in venv

        d = _agents_dir()
        if not d.exists():
            return {"agents": []}
        agents: list[dict[str, Any]] = []
        for f in sorted(d.glob("*.yaml")):
            try:
                data = _yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                agents.append(
                    {
                        "id": f.stem,
                        "name": data.get("name", f.stem),
                        "description": data.get("description", ""),
                        "model": data.get("model", ""),
                        "tools": data.get("tools", []),
                        "risk_level": data.get("risk_level", "low"),
                        "system_prompt": data.get("system_prompt", ""),
                    }
                )
            except Exception as yaml_err:
                logger.warning("Failed to parse agent file %s: %s", f, yaml_err)
        return {"agents": agents}
    except Exception as e:
        logger.warning("GET /agents failed: %s", e)
        return {"agents": []}


@app.post("/agents")
async def create_agent(request: Request) -> dict[str, Any]:
    """Create a new agent definition YAML file in the agents/ folder."""
    try:
        import re as _re

        import yaml as _yaml

        body = await request.json()
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")

        # Sanitize filename: lowercase, spaces → hyphens, strip non-alphanumeric
        slug = _re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
        if not slug:
            raise HTTPException(status_code=400, detail="name produces an empty filename")

        d = _agents_dir()
        d.mkdir(parents=True, exist_ok=True)
        target = d / f"{slug}.yaml"
        if target.exists():
            raise HTTPException(status_code=409, detail=f"Agent '{slug}' already exists")

        agent_data: dict[str, Any] = {
            "name": name,
            "description": body.get("description", ""),
            "system_prompt": body.get("system_prompt", ""),
            "model": body.get("model", ""),
            "tools": body.get("tools", []),
            "risk_level": body.get("risk_level", "low"),
        }
        target.write_text(_yaml.dump(agent_data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        logger.info("Created agent definition: %s", target)
        return {"id": slug, "status": "created", **agent_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("POST /agents failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
