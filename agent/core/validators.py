"""Path and command validators — constrain file ops to safe directories."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_USER_HOME = Path(os.path.expanduser("~"))
_TEMP_DIR = Path(os.environ.get("TEMP", os.environ.get("TMP", "/tmp")))

# Paths that must never be agent-writable — even though they sit inside SAFE_WRITE_ROOTS.
# Checked before the allowlist to prevent persistent code injection via plugin directory.
_BLOCKED_WRITE_PATHS: list[Path] = [
    _PROJECT_ROOT / "agent" / "plugins",
    _PROJECT_ROOT / "agent" / "core",
    _PROJECT_ROOT / "run_wake_listener.py",
    _PROJECT_ROOT / "launch.py",
]

# Explicit read-allowed subdirs — do NOT include all of _USER_HOME (exposes .ssh, .aws, etc.)
SAFE_READ_ROOTS: list[Path] = [
    _PROJECT_ROOT,
    _USER_HOME / "Documents",
    _USER_HOME / "Downloads",
    _USER_HOME / "Desktop",
    _USER_HOME / "AppData" / "Local" / "Roamin",
    _TEMP_DIR,
]

# Directories where write/delete operations are allowed (stricter)
SAFE_WRITE_ROOTS: list[Path] = [
    _PROJECT_ROOT,
    _TEMP_DIR,
]


def validate_path(path: str, mode: str = "read") -> dict | None:
    """Validate a file path against the allowlist.

    Returns None if the path is safe, or a failure dict if rejected.
    mode: "read" uses SAFE_READ_ROOTS, "write" uses SAFE_WRITE_ROOTS.
    """
    if not path:
        return {"success": False, "error": "No path provided", "category": "validation"}

    # Reject null bytes (path injection vector)
    if "\x00" in path:
        return {"success": False, "error": "Path contains null bytes", "category": "validation"}

    try:
        # Resolve symlinks and normalize to absolute path
        resolved = Path(path).resolve()
    except (OSError, ValueError) as e:
        return {"success": False, "error": f"Invalid path: {e}", "category": "validation"}

    # Reject UNC paths (\\server\share)
    path_str = str(resolved)
    if path_str.startswith("\\\\"):
        return {"success": False, "error": "UNC paths are not allowed", "category": "validation"}

    # Denylist check for writes — blocked paths take priority over allowlist
    if mode == "write":
        for blocked in _BLOCKED_WRITE_PATHS:
            try:
                resolved.relative_to(blocked.resolve())
                return {
                    "success": False,
                    "error": (
                        f"Path '{resolved}' is a protected system directory. "
                        "Agent writes to plugin and core directories are not allowed."
                    ),
                    "category": "permission",
                }
            except ValueError:
                continue

    # Pick allowlist based on mode
    roots = SAFE_WRITE_ROOTS if mode == "write" else SAFE_READ_ROOTS

    # Check if resolved path is under any allowed root
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return None  # Safe — path is under an allowed root
        except ValueError:
            continue

    # Path is outside all allowed roots
    allowed = ", ".join(str(r) for r in roots)
    return {
        "success": False,
        "error": f"Path '{resolved}' is outside allowed directories ({allowed})",
        "category": "permission",
    }
