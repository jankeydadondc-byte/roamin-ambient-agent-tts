"""
settings_store.py — Persistent user settings backed by config/settings.local.json.

All writes are atomic (write-to-temp then rename) to prevent corruption on crash.
Callers import the module-level helpers; no need to instantiate anything.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from agent.core.paths import get_project_root

logger = logging.getLogger(__name__)

_SETTINGS_PATH: Path | None = None  # resolved lazily


def _path() -> Path:
    global _SETTINGS_PATH
    if _SETTINGS_PATH is None:
        cfg_dir = get_project_root() / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        _SETTINGS_PATH = cfg_dir / "settings.local.json"
    return _SETTINGS_PATH


_DEFAULTS: dict[str, Any] = {
    "volume": 1.0,
    "screenshots_enabled": True,
    "always_on_top": False,
    "default_model": "",
    "model_overrides": {},  # task -> model_id
    "tool_states": {},  # tool_name -> bool (True = enabled)
    "model_params": {  # inference parameters applied to all models
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 2048,
        "context_length": 8192,
    },
    "model_scan_paths": [  # directories to scan for GGUF files
        r"C:\AI\roamin-ambient-agent-tts\models",
    ],
}


def load() -> dict[str, Any]:
    """Load settings from disk, merging with defaults for any missing keys."""
    p = _path()
    if not p.exists():
        return dict(_DEFAULTS)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        merged = dict(_DEFAULTS)
        merged.update(raw)
        return merged
    except Exception as exc:
        logger.warning("[settings_store] Failed to load %s: %s", p, exc)
        return dict(_DEFAULTS)


def save(settings: dict[str, Any]) -> None:
    """Atomically write settings dict to disk."""
    p = _path()
    try:
        # Write to a temp file in the same directory, then rename (atomic on Windows NTFS)
        fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, p)
        logger.debug("[settings_store] Saved settings to %s", p)
    except Exception as exc:
        logger.error("[settings_store] Failed to save settings: %s", exc)


def get(key: str, default: Any = None) -> Any:
    """Read a single key from persisted settings."""
    return load().get(key, default)


def set_value(key: str, value: Any) -> None:
    """Update a single key and persist."""
    settings = load()
    settings[key] = value
    save(settings)


def update(updates: dict[str, Any]) -> None:
    """Merge *updates* into the settings file."""
    settings = load()
    settings.update(updates)
    save(settings)
