"""Path and command validators — constrain file ops to safe directories."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_USER_HOME = Path(os.path.expanduser("~"))
_TEMP_DIR = Path(os.environ.get("TEMP", os.environ.get("TMP", "/tmp")))

# Directories where read operations are allowed
SAFE_READ_ROOTS: list[Path] = [
    _PROJECT_ROOT,
    _USER_HOME,
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
