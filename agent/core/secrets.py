"""Centralized secrets loader — .env file + env var fallback."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOADED = False


def load_secrets(env_path: Path | None = None) -> None:
    """Load secrets from .env file into os.environ (env vars take precedence)."""
    global _LOADED
    if _LOADED:
        return

    path = env_path or _PROJECT_ROOT / ".env"
    if not path.exists():
        logger.debug("No .env file at %s — using environment variables only", path)
        _LOADED = True
        return

    # Parse .env manually (no external dependency needed for simple KEY=VALUE)
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        # Skip comments and blank lines
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        # Env vars take precedence over .env file values
        if key not in os.environ:
            os.environ[key] = value
            count += 1

    logger.info("Loaded %d secret(s) from %s", count, path)
    _LOADED = True


def get_secret(name: str, required: bool = False) -> str | None:
    """Get a secret by name from environment.

    Call load_secrets() first to populate from .env file.
    """
    value = os.environ.get(name)
    if value is None and required:
        raise RuntimeError(f"Required secret '{name}' not found in environment or .env file")
    return value


def check_secrets(required: list[str] | None = None, optional: list[str] | None = None) -> None:
    """Validate required secrets at startup, warn about missing optional ones."""
    for name in required or []:
        if not os.environ.get(name):
            raise RuntimeError(f"Required secret '{name}' not set — add to .env or environment")

    for name in optional or []:
        if not os.environ.get(name):
            logger.info("Optional secret '%s' not set — feature may be limited", name)
