"""Convenience runner for the Control API (development).

Run with:

    python run_control_api.py

This assumes `fastapi` and `uvicorn` are installed in the active environment.
"""

from __future__ import annotations

import atexit
import ctypes
import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path

import uvicorn

from agent.core import paths, ports

_PROJECT_ROOT = Path(__file__).parent
_LOCK_FILE = _PROJECT_ROOT / "logs" / "_control_api.lock"
_DISCOVERY_FILE = _PROJECT_ROOT / ".loom" / "control_api_port.json"
_MUTEX_NAME = "Global\\RoaminControlAPI"


def _acquire_single_instance_mutex() -> object:
    """Acquire a named Windows mutex. Returns handle, or None if already held.

    The OS releases the mutex automatically on any process exit — normal,
    crash, or SIGKILL — so there is never a stale mutex left behind.
    """
    handle = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    err = ctypes.windll.kernel32.GetLastError()
    if err == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(handle)
        return None
    return handle


def _write_pid_files(port: int) -> None:
    """Write PID lock file and discovery file on startup."""
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LOCK_FILE.write_text(str(os.getpid()))

    _DISCOVERY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DISCOVERY_FILE.write_text(json.dumps({"pid": os.getpid(), "port": port}))


def _cleanup_pid_files() -> None:
    """Remove PID lock and discovery files on exit."""
    for f in (_LOCK_FILE, _DISCOVERY_FILE):
        try:
            if f.exists():
                f.unlink()
        except OSError:
            pass


def _setup_logging() -> None:
    """Configure logging to capture both uvicorn and app logs to file."""
    project_root = paths.get_project_root()
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "control_api.log"

    # Configure root logger with file handler
    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=3,
    )
    formatter = logging.Formatter("%(levelname)s:     %(message)s")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def main() -> None:
    # Single-instance guard — named mutex prevents duplicate control_api processes
    # no matter how they were started (VBS, PowerShell, manual, or as a sidecar).
    _mutex = _acquire_single_instance_mutex()
    if _mutex is None:
        print("[Control API] Already running (mutex held). Exiting.")
        sys.exit(0)

    _setup_logging()
    port = int(os.environ.get("ROAMIN_CONTROL_API_PORT") or ports.CONTROL_API_DEFAULT_PORT)

    # Write PID lock + discovery file so launch.py and kill scripts can find us
    _write_pid_files(port)
    atexit.register(_cleanup_pid_files)

    uvicorn.run("agent.control_api:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
