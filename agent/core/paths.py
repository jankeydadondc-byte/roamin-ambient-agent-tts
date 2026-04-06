"""
Agent Core - Path Resolution and Management

Handles project root discovery, workspace paths, and canonical path operations.
Extracted from monolithic agent.py during module split refactor.
"""

import os
import pathlib
from pathlib import Path


def find_project_root(start_path: Path | None = None) -> Path:
    """
    Find the project root by looking for .roamin_root marker or roamin_windsurf_bridge.py.

    Args:
        start_path: Starting path for search. Defaults to current file's directory.

    Returns:
        Path to project root

    Raises:
        RuntimeError: If no project root marker is found
    """
    if start_path is None:
        start_path = Path(__file__).parent.parent.absolute()  # Go up from agent/core/

    current = Path(start_path).absolute()

    # Walk up parent chain looking for markers
    for parent in [current] + list(current.parents):
        # Check for .roamin_root marker file
        if (parent / ".roamin_root").exists():
            return parent

        # Check for bridge file as fallback
        if (parent / "roamin_windsurf_bridge.py").exists():
            return parent

        # Stop at filesystem root
        if parent.parent == parent:
            break

    # Fallback: use the directory containing this module's parent
    fallback = Path(__file__).resolve().parents[1]
    if (fallback / "roamin_windsurf_bridge.py").exists():
        return fallback

    raise RuntimeError(
        f"Project root not found - no .roamin_root or roamin_windsurf_bridge.py found in parent chain from {start_path}"
    )


def get_workspace_dir(project_root: Path | None = None) -> Path:
    """Get the workspace directory path."""
    if project_root is None:
        project_root = find_project_root()

    return project_root / "workspace"


def get_logs_root(project_root: Path | None = None) -> Path:
    """Get the logs root directory path."""
    if project_root is None:

        project_root = find_project_root()
    return project_root / "logs" / "bridge_runs"


def get_quarantine_root(project_root: Path | None = None) -> Path:
    """Get the quarantine root directory path."""

    if project_root is None:
        project_root = find_project_root()

    return project_root / "quarantine"


def get_config_path(project_root: Path | None = None) -> Path:
    """Get the bridge configuration file path."""
    if project_root is None:

        project_root = find_project_root()
    return project_root / "bridge_config.json"


def normalize_path(p: pathlib.Path) -> str:
    """
    Canonicalize to absolute, normalized-case path. Never throws; fallback to str(p).

    Args:
        p: Path to normalize

    Returns:
        Normalized absolute path string
    """
    try:
        abspath = os.path.abspath(str(p))
        return os.path.normcase(abspath)

    except Exception:
        try:

            return os.path.normcase(str(p))
        except Exception:

            return str(p)


def is_under_root(path_str: str, root_str: str) -> bool:
    """
    Boundary-safe "under root" check using commonpath. Cross-drive safe.

    Args:
        path_str: Path to check
        root_str: Root path to check against

    Returns:
        True if path is under root, False otherwise
    """
    try:
        path = os.path.normcase(os.path.abspath(path_str))
        root = os.path.normcase(os.path.abspath(root_str))

        return os.path.commonpath([path, root]) == root
    except Exception:
        return False


# Cache for project root to avoid repeated filesystem traversal


_PROJECT_ROOT_CACHE: Path | None = None


def get_project_root() -> Path:
    """Get cached project root, discovering it on first call."""
    global _PROJECT_ROOT_CACHE

    if _PROJECT_ROOT_CACHE is None:
        _PROJECT_ROOT_CACHE = find_project_root()
    return _PROJECT_ROOT_CACHE


def reset_project_root_cache() -> None:
    """Reset the project root cache (for testing)."""
    global _PROJECT_ROOT_CACHE
    _PROJECT_ROOT_CACHE = None


# P3 Settings Path Management


def get_config_dir() -> Path:
    """
    Get the canonical configuration directory.



    Returns:
        Path to the config directory under project root


    """

    return get_project_root() / "config"


def get_settings_schema_path() -> Path:
    """


    Get the path to the settings JSON schema.

    Returns:


        Path to settings.schema.json
    """
    return get_config_dir() / "settings.schema.json"


def get_settings_defaults_path() -> Path:
    """
    Get the path to the default settings.


    Returns:
        Path to settings.defaults.json
    """
    return get_config_dir() / "settings.defaults.json"


def get_settings_user_path() -> Path:
    """
    Get the path to user-specific settings.



    Returns:
        Path to settings.local.json (may not exist)
    """
    return get_config_dir() / "settings.local.json"


def get_settings_backup_dir() -> Path:
    """


    Get the path to settings backup directory.

    Returns:


        Path to config/backups/settings/


    """

    return get_config_dir() / "backups" / "settings"


def get_safe_mode_env_var() -> str:
    """
    Get the Safe Mode environment variable name.

    Returns:


        Environment variable name for Safe Mode detection


    """

    return "ROAMIN_SAFE_MODE"


def is_safe_mode_active() -> bool:
    """
    Check if Safe Mode is currently active.

    Returns:
        True if Safe Mode is active, False otherwise
    """
    # Safe Mode is OFF by default, ON only when explicitly enabled via ROAMIN_SAFE_MODE=1
    return bool(int(os.environ.get(get_safe_mode_env_var(), "0")))


# Backward compatibility constants for existing code

# These will be removed in later phases once all imports are updated
# Guard project root discovery at import time so unit tests and tooling that
# import this module from arbitrary locations don't raise at import time.
try:
    PROJECT_ROOT = get_project_root()
except Exception:
    from pathlib import Path

    PROJECT_ROOT = Path.cwd()

WORKSPACE_DIR = get_workspace_dir(PROJECT_ROOT)
CONFIG_FILE = get_config_path(PROJECT_ROOT)
