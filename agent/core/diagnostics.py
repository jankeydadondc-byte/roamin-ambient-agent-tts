from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from fastapi import APIRouter

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent
BRIDGE_STATE_FILE = PROJECT_ROOT / "bridge_state.json"


def _read_bridge_state() -> dict:
    try:
        if BRIDGE_STATE_FILE.exists():
            with open(BRIDGE_STATE_FILE, encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        pass
    return {}


@router.get("/diagnostics")
def diagnostics() -> dict:
    """Return small non-secret diagnostics for UI polling.

    Fields:
      - server_pid: PID of control API process
      - uptime_seconds: seconds since process start (approx)
      - started_utc: ISO timestamp when server believed it started
      - oauth_ready: bool (non-secret) whether a calendar token exists
      - oauth_scopes: list of scopes found (may be empty)
      - bridge_state: minimal bridge_state.json contents (non-secret)
    """
    # now is intentionally unused; kept for potential future timing checks
    _ = datetime.now(timezone.utc)

    # Server PID and start time
    server_pid = os.getpid()
    started_utc = None
    uptime_seconds = None
    try:
        # Try to get start time from process info via psutil if available
        import psutil

        p = psutil.Process(server_pid)
        started_utc = datetime.fromtimestamp(p.create_time(), timezone.utc).isoformat()
        uptime_seconds = int(time.time() - p.create_time())
    except Exception:
        started_utc = None
        uptime_seconds = None

    # OAuth metadata (non-secret)
    oauth_ready = False
    oauth_scopes = []
    try:
        # reuse existing helper if present
        from agent.core.oauth_health import _load_token_metadata

        meta = _load_token_metadata()
        oauth_ready = bool(meta.get("ready"))
        oauth_scopes = meta.get("scopes") or []
    except Exception:
        # If helper not present or fails, leave defaults
        pass

    bridge_state = _read_bridge_state()

    return {
        "server_pid": server_pid,
        "started_utc": started_utc,
        "uptime_seconds": uptime_seconds,
        "oauth_ready": oauth_ready,
        "oauth_scopes": oauth_scopes,
        "bridge_state": {"pid": bridge_state.get("pid"), "status": bridge_state.get("status")},
    }
