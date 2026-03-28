"""
Agent Core - Configuration Management

Handles configuration loading, validation, and hashing.
Extracted from monolithic bridge and API server during module split refactor.

YAML Spec Loader for Canonical Agent
"""

import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

# --- Canonical Agent YAML Loader ---
import yaml

SPEC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".github", "agents", "roamin.main.agent.yaml"
)

_agent_spec_cache = None


def load_agent_spec(path: str = SPEC_PATH):
    global _agent_spec_cache
    if _agent_spec_cache is not None:
        return _agent_spec_cache
    with open(path, encoding="utf-8") as f:
        _agent_spec_cache = yaml.safe_load(f)
    return _agent_spec_cache


def get_canonical_features():
    spec = load_agent_spec()
    return spec.get("canonical_features", [])


def get_metadata():
    spec = load_agent_spec()
    return spec.get("metadata", {})


def get_persona():
    spec = load_agent_spec()
    return spec.get("persona", {})


def get_system_prompt():
    spec = load_agent_spec()
    return spec.get("model_config", {}).get("system_prompt", {}).get("base", "You are Roamin.")


def get_tools():
    spec = load_agent_spec()
    return spec.get("tools", [])


def get_permissions():
    spec = load_agent_spec()
    return spec.get("permissions", {})


def get_validation():
    spec = load_agent_spec()
    return spec.get("validation", {})


def get_io_schema():
    spec = load_agent_spec()
    return spec.get("io_schema", {})


from agent.core.paths import get_config_path, get_project_root  # noqa: E402

# Default configuration - matches roamin_windsurf_bridge.py
DEFAULT_CONFIG: dict[str, Any] = {
    "promote": {"target_dir": "promoted"},
    "quarantine": {"enabled": True, "root_dir": "quarantine"},
    "whitelist": ["*.py"],  # default whitelist
    "debounce_seconds": 2.0,
    "ai_timeout_seconds": 120,
    "feature_flags": {
        "auto_promote": True,
        "auto_fix": False,  # disabled by default for safety
        "ask_confirm_on_patch": True,
        "max_fix_attempts": 3,
    },
}

# Global configuration state - loaded from bridge_config.json
CONFIG: dict[str, Any] = DEFAULT_CONFIG.copy()


def load_bridge_config(config_file_path: Path | None = None) -> dict[str, Any]:
    """
    Load bridge_config.json with safe merging and BOM support.

    Args:
        config_file_path: Optional path to config file. Uses default if None.

    Returns:
        Dictionary with loaded configuration

    Side Effects:
        Updates global CONFIG dictionary
    """
    if config_file_path is None:
        config_file_path = get_config_path()

    try:
        with open(config_file_path, encoding="utf-8-sig") as f:
            user_config = json.load(f)

        # Shallow merge with two-level dicts
        for k, v in user_config.items():
            if isinstance(v, dict) and isinstance(CONFIG.get(k), dict):
                CONFIG[k].update(v)
            else:
                CONFIG[k] = v

        logging.debug("Loaded config (utf-8-sig) from %s", config_file_path)

    except Exception as e:
        logging.debug("Using defaults; failed to load %s: %s", config_file_path, e)

    return CONFIG


def get_config_hash(config_file_path: Path | None = None) -> str:
    """
    Get bridge_config.json hash for fingerprinting and change detection.

    Args:
        config_file_path: Optional path to config file. Uses default if None.

    Returns:
        First 8 characters of SHA256 hash, or "no-config" if file doesn't exist
    """
    if config_file_path is None:
        config_file_path = get_config_path()

    if config_file_path.exists():
        try:
            content = config_file_path.read_text(encoding="utf-8")
            return hashlib.sha256(content.encode()).hexdigest()[:8]
        except Exception as e:
            logging.debug("Failed to hash config file %s: %s", config_file_path, e)
            return "hash-error"

    return "no-config"


def get_version_info() -> dict[str, str]:
    """
    Get version information including Python version, git describe, and build info.

    Returns:
        Dictionary with version details
    """
    version_info = {
        "python_version": sys.version.split()[0],
        "build_tag": "dev-build",
        "git_describe": "unknown",
    }

    # Try to get git version info
    try:
        project_root = get_project_root()
        git_result = subprocess.run(
            ["git", "describe", "--tags", "--dirty", "--always"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if git_result.returncode == 0:
            git_describe = git_result.stdout.strip()
            version_info["git_describe"] = git_describe
            version_info["build_tag"] = git_describe
    except Exception as e:
        logging.debug("Failed to get git version info: %s", e)

    return version_info


def validate_config_schema(config: dict[str, Any]) -> bool:
    """
    Validate that the loaded configuration has the expected structure.

    Args:
        config: Configuration dictionary to validate

    Returns:
        True if valid, False otherwise
    """
    # Basic validation - can be expanded as needed
    try:
        # Check required top-level structure
        if not isinstance(config, dict):
            return False

        # Validate target_dir if present
        if "target_dir" in config and not isinstance(config["target_dir"], str):
            return False

        # Validate feature_flags if present
        if "feature_flags" in config:
            if not isinstance(config["feature_flags"], dict):
                return False

        # Validate checks if present
        if "checks" in config:
            if not isinstance(config["checks"], dict):
                return False

        return True

    except Exception as e:
        logging.debug("Config validation failed: %s", e)

        return False


def get_config() -> dict[str, Any]:
    """
    Get the current global configuration.


    Returns:
        Current CONFIG dictionary


    """
    return CONFIG


def update_config(updates: dict[str, Any], save_to_file: bool = False) -> None:
    """
    Update the global configuration with new values.

    Args:
        updates: Dictionary of updates to apply
        save_to_file: Whether to save changes back to config file
    """
    # Apply updates with shallow merge for nested dicts
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(CONFIG.get(k), dict):
            CONFIG[k].update(v)

        else:
            CONFIG[k] = v

    if save_to_file:

        save_config_to_file()


def save_config_to_file(config_file_path: Path | None = None) -> None:
    """
    Save the current CONFIG to the config file.

    Args:
        config_file_path: Optional path to config file. Uses default if None.
    """
    if config_file_path is None:
        config_file_path = get_config_path()

    try:
        with open(config_file_path, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f, indent=2)
        logging.debug("Saved config to %s", config_file_path)

    except Exception as e:

        logging.error("Failed to save config to %s: %s", config_file_path, e)


def reset_config_to_defaults() -> None:
    """Reset the global CONFIG to default values."""
    global CONFIG

    CONFIG = DEFAULT_CONFIG.copy()


# Backward compatibility - matches bridge usage
def load_bridge_config_legacy() -> None:
    """Legacy function name for backward compatibility."""
    load_bridge_config()
