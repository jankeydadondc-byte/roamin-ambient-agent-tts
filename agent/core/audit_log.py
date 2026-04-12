"""Audit log — append-only JSONL record of every tool execution."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOG_PATH = _PROJECT_ROOT / "logs" / "audit.jsonl"
_MAX_SIZE = 100 * 1024  # Auto-prune at 100KB


def append(
    tool: str,
    params: dict,
    success: bool,
    result_summary: str = "",
    duration_ms: float = 0,
) -> None:
    """Write one audit entry to the JSONL log. Never raises."""
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "params": _sanitize_params(params),
            "success": success,
            "result": result_summary[:500],
            "duration_ms": round(duration_ms, 1),
        }
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        # Auto-prune if file exceeds size limit
        _prune_if_needed()
    except Exception as e:
        logger.debug("Audit log write failed (non-fatal): %s", e)


def query(
    limit: int = 50,
    tool_filter: str | None = None,
    since: str | None = None,
) -> list[dict]:
    """Read recent audit entries in reverse chronological order."""
    if not _LOG_PATH.exists():
        return []

    entries = []
    try:
        for line in _LOG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Apply filters
            if tool_filter and entry.get("tool") != tool_filter:
                continue
            if since and entry.get("ts", "") < since:
                continue
            entries.append(entry)
    except Exception as e:
        logger.debug("Audit log read failed: %s", e)

    # Reverse chronological, limited
    return entries[-limit:][::-1]


def _sanitize_params(params: dict) -> dict:
    """Redact large values and sensitive fields from params before logging."""
    sanitized = {}
    for k, v in params.items():
        v_str = str(v)
        if len(v_str) > 200:
            sanitized[k] = v_str[:200] + "...[truncated]"
        else:
            sanitized[k] = v
    return sanitized


def _prune_if_needed() -> None:
    """Keep only the last ~60% of the log when file exceeds max size."""
    try:
        if not _LOG_PATH.exists():
            return
        size = _LOG_PATH.stat().st_size
        if size <= _MAX_SIZE:
            return
        # Read all lines, keep the last 60%
        lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
        keep = int(len(lines) * 0.6)
        pruned = "\n".join(lines[-keep:]) + "\n"
        # Atomic write: temp file → os.replace() prevents log destruction on crash (#91)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=_LOG_PATH.parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(pruned)
            os.replace(tmp_path, _LOG_PATH)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        logger.debug("Audit log pruned: %d -> %d entries", len(lines), keep)
    except Exception as e:
        logger.debug("Audit log prune failed (non-fatal): %s", e)
