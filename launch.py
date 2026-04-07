"""Roamin Unified Launcher

Run with:
    python launch.py

Detects and terminates any stale/duplicate Roamin processes, then
launches all components fresh in their own console windows:
  - Roamin wake listener (which spawns the Control API as a sidecar)
  - Vite dev server for the Control Panel UI
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
LOCK_FILE = PROJECT_ROOT / "logs" / "_wake_listener.lock"
DISCOVERY_FILE = PROJECT_ROOT / ".loom" / "control_api_port.json"
UI_DIR = PROJECT_ROOT / "ui" / "control-panel"

VITE_PORT = 5173
CONTROL_API_PORTS = range(8765, 8776)


# ---------------------------------------------------------------------------
# Process utilities
# ---------------------------------------------------------------------------


def _is_process_running(pid: int) -> bool:
    """Return True if a process with the given PID is currently alive."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid(pid: int, label: str = "") -> bool:
    """Kill a process tree by PID on Windows using taskkill /T /F."""
    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  [killed] {label} (PID {pid})")
            return True
        # Process may have already exited — not a failure
        return False
    except Exception as e:
        print(f"  [warn]   Could not kill {label} (PID {pid}): {e}")
        return False


def _pids_on_ports(ports: range | list[int]) -> dict[int, int]:
    """Return {pid: port} for any process listening on the given ports.

    Uses ``netstat -ano -p TCP`` which is available on all modern Windows.
    """
    found: dict[int, int] = {}
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            upper = line.upper()
            if "LISTENING" not in upper:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            # Local address is parts[1], e.g. "127.0.0.1:8765" or "0.0.0.0:8765"
            local_addr = parts[1]
            pid_str = parts[-1]
            try:
                port = int(local_addr.rsplit(":", 1)[-1])
                pid = int(pid_str)
            except ValueError:
                continue
            if port in ports:
                found[pid] = port
    except Exception:
        pass
    return found


# ---------------------------------------------------------------------------
# Stop stale instances
# ---------------------------------------------------------------------------


def stop_stale_instances() -> bool:
    """Detect and terminate any running duplicates.  Returns True if anything was killed."""
    print("[Launcher] Checking for stale instances...")

    pids_to_kill: dict[int, str] = {}

    # Layer 1: Wake listener lock file
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            if pid > 0 and _is_process_running(pid):
                pids_to_kill[pid] = "Roamin wake listener"
        except (ValueError, IOError):
            pass

    # Layer 2: Control API discovery file
    if DISCOVERY_FILE.exists():
        try:
            data = json.loads(DISCOVERY_FILE.read_text())
            pid = int(data.get("pid", 0))
            if pid > 0 and pid not in pids_to_kill and _is_process_running(pid):
                pids_to_kill[pid] = "Control API"
        except (ValueError, KeyError, IOError, json.JSONDecodeError):
            pass

    # Layer 3: Port scan fallback — catch anything on our known ports
    scan_ports = list(CONTROL_API_PORTS) + [VITE_PORT]
    for pid, port in _pids_on_ports(scan_ports).items():
        if pid not in pids_to_kill:
            label = "Vite dev server" if port == VITE_PORT else f"Control API (port {port})"
            pids_to_kill[pid] = label

    if not pids_to_kill:
        print("[Launcher] No stale instances found.\n")
        return False

    print(f"[Launcher] Found {len(pids_to_kill)} stale instance(s) — terminating:")
    for pid, label in pids_to_kill.items():
        _kill_pid(pid, label)

    # Clean up stale discovery/lock files so new processes start cleanly
    for f in (LOCK_FILE, DISCOVERY_FILE):
        try:
            if f.exists():
                f.unlink()
        except IOError:
            pass

    # Brief pause to let the OS release ports
    print("[Launcher] Waiting for ports to clear...")
    time.sleep(1.5)
    print()
    return True


# ---------------------------------------------------------------------------
# Launch everything
# ---------------------------------------------------------------------------


def launch_all() -> None:
    """Spawn all Roamin components in their own console windows."""
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)  # Windows only; no-op on other platforms

    # --- Roamin wake listener (spawns Control API as sidecar automatically) ---
    print("[Launcher] Starting Roamin...")
    subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "run_wake_listener.py")],
        cwd=str(PROJECT_ROOT),
        creationflags=flags,
    )

    # --- Vite dev server ---
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    print("[Launcher] Starting Vite dev server...")
    subprocess.Popen(
        [npm_cmd, "run", "dev", "--", "--host", "127.0.0.1"],
        cwd=str(UI_DIR),
        creationflags=flags,
    )

    print()
    print("[Launcher] All systems go!")
    print(f"  Control Panel UI → http://127.0.0.1:{VITE_PORT}")
    print("  Control API      → http://127.0.0.1:8765")
    print()
    print("[Launcher] Done. Two console windows are now open.")
    print("           Close them individually, or re-run launch.py to restart everything.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("  Roamin Unified Launcher")
    print("=" * 60)
    print()
    stop_stale_instances()
    launch_all()


if __name__ == "__main__":
    main()
