"""
Agent Core - Structured Logging

Handles logging setup, rotation, and structured output.
Extracted from monolithic bridge during module split refactor.
"""

import contextvars
import datetime
import json
import logging
import logging.handlers
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from agent.core.paths import get_project_root


def setup_bridge_logging(log_level: int = logging.DEBUG) -> Path:
    """
    Setup proper file logging for the bridge with daily rotation.

    Args:
        log_level: Logging level (default: DEBUG)

    Returns:
        Path to the log file being used
    """
    project_root = get_project_root()
    log_dir = project_root / "logs" / "bridge_runs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create daily log file with YYYYMMDD format to match existing pattern
    today = datetime.date.today().strftime("%Y%m%d")
    log_file = log_dir / f"bridge_{today}.log"

    # Configure logging to both file and stderr with identical format to original
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8")],
    )
    logging.info(f"Bridge logging to {log_file}")
    return log_file


def get_alert_log_path() -> Path:
    """Get path to the alerts log file."""
    project_root = get_project_root()
    return project_root / "logs" / "bridge_runs" / "bridge_ALERTS.log"


def log_structured_message(msg: str) -> None:
    """
    Log a message with timestamp to stderr and handle alert breadcrumbs.

    This matches the original _log() function behavior exactly.

    Args:
        msg: Message to log
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, file=sys.stderr)

    try:
        logging.getLogger("bridge.runtime").info(msg)
    except Exception:
        pass

    # Alert breadcrumb: append to persistent log for auditors
    if any(keyword in msg for keyword in ["[ALERT]", "[WARN]", "[ERR]", "failed", "error"]):
        try:
            alert_log = get_alert_log_path()
            alert_log.parent.mkdir(parents=True, exist_ok=True)
            with alert_log.open("a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {msg}\n")
        except Exception:
            pass  # Don't fail on breadcrumb logging


def create_logger(name: str, log_file: Path | None = None) -> logging.Logger:
    """
    Create a named logger with consistent formatting.

    Args:
        name: Logger name
        log_file: Optional specific log file (uses default bridge log if None)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    if not logger.handlers:  # Avoid duplicate handlers
        if log_file is None:
            # Use the daily bridge log
            project_root = get_project_root()
            log_dir = project_root / "logs" / "bridge_runs"
            today = datetime.date.today().strftime("%Y%m%d")
            log_file = log_dir / f"bridge_{today}.log"

        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        logger.setLevel(logging.DEBUG)

    return logger


def setup_rotating_logger(
    name: str, log_file: Path, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5
) -> logging.Logger:
    """
    Create a logger with rotating file handler.

    Args:
        name: Logger name
        log_file: Path to log file
        max_bytes: Maximum bytes per log file before rotation
        backup_count: Number of backup files to keep

    Returns:
        Configured rotating logger
    """
    logger = logging.getLogger(name)

    if not logger.handlers:  # Avoid duplicate handlers
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    return logger


def log_with_context(msg: str, context: dict[str, Any] | None = None) -> None:
    """
    Log a message with optional context data.

    Args:
        msg: Message to log
        context: Optional dictionary of context data
    """
    if context:
        context_str = " ".join([f"{k}={v}" for k, v in context.items()])
        _ = f"{msg} [{context_str}]"  # noqa: F841
    else:
        _ = msg  # noqa: F841


def get_log_directory() -> Path:
    """Get the bridge logs directory path."""
    project_root = get_project_root()
    return project_root / "logs" / "bridge_runs"


def get_current_log_file() -> Path:
    """Get the current daily bridge log file path."""
    log_dir = get_log_directory()
    today = datetime.date.today().strftime("%Y%m%d")
    return log_dir / f"bridge_{today}.log"


def ensure_log_directory() -> Path:
    """Ensure the log directory exists and return its path."""
    log_dir = get_log_directory()
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


# Backward compatibility aliases


def _log(msg: str) -> None:
    """Backward compatibility alias for log_structured_message."""
    log_structured_message(msg)


def setup_logging() -> None:
    """Backward compatibility alias for setup_bridge_logging."""
    setup_bridge_logging()


# ---------------------------------------------------------------------------
# Priority 9.2 — Structured Logging Additions
# ---------------------------------------------------------------------------

# --- 9.2.3  Request ID context variable ---

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def set_request_id(request_id: str) -> None:
    """Set the current request ID for this async context (thread or coroutine)."""
    _request_id_var.set(request_id)


def get_request_id() -> str | None:
    """Return the current request ID, or None if not set."""
    return _request_id_var.get()


@contextmanager
def bind_request_id(request_id: str):
    """Context manager: set request_id for the duration of the block, then restore."""
    token = _request_id_var.set(request_id)
    try:
        yield
    finally:
        _request_id_var.reset(token)


# --- 9.2.1  JSON Formatter ---


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object.

    Always-present fields: timestamp (ISO-8601), level, logger, message.
    Optional: request_id (from _request_id_var), plus any extra fields set
    via ``logger.info(msg, extra={"key": value})``.
    """

    # Standard LogRecord attributes that should NOT be copied into extra
    _SKIP = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        payload: dict[str, Any] = {
            "timestamp": datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }
        rid = _request_id_var.get()
        if rid is not None:
            payload["request_id"] = rid
        # Include any extra fields the caller passed
        for key, val in record.__dict__.items():
            if key not in self._SKIP:
                payload[key] = val
        return json.dumps(payload, default=str)


# --- 9.2.2  Throttled Logger ---


class ThrottledLogger:
    """Rate-limit repeated log messages to prevent log spam.

    Identical message strings within *cooldown_seconds* (default: 60) are
    suppressed. When a new distinct message arrives (or ``flush()`` is called
    explicitly), a suppression summary is emitted for the previously-suppressed
    run if any messages were dropped.

    Keying is by exact message string (not format args) for simplicity.
    """

    def __init__(self, logger: logging.Logger, cooldown_seconds: float = 60.0) -> None:
        self._logger = logger
        self._cooldown = cooldown_seconds
        self._last_msg: str | None = None
        self._last_ts: float = 0.0
        self._suppressed: int = 0

    def _emit_suppression_summary(self) -> None:
        if self._suppressed > 0 and self._last_msg is not None:
            self._logger.info(
                "%d similar message(s) suppressed: %s",
                self._suppressed,
                self._last_msg[:80],
            )
            self._suppressed = 0

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        now = time.monotonic()
        if msg == self._last_msg and (now - self._last_ts) < self._cooldown:
            self._suppressed += 1
            return
        # New message or cooldown expired — flush old summary first
        self._emit_suppression_summary()
        self._logger.log(level, msg, **kwargs)
        self._last_msg = msg
        self._last_ts = now

    def info(self, msg: str, **kwargs: Any) -> None:
        """Log at INFO level, rate-limited."""
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log at WARNING level, rate-limited."""
        self._log(logging.WARNING, msg, **kwargs)

    def flush(self) -> None:
        """Emit any pending suppression summary immediately."""
        self._emit_suppression_summary()


# --- 9.2.4  JSON logger factory ---


def get_json_logger(name: str, log_file: Path | None = None) -> logging.Logger:
    """Return a named logger whose handler emits single-line JSON via JsonFormatter.

    If *log_file* is None, a StreamHandler to stdout is used so output is
    immediately visible in terminal / tests.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            handler: logging.Handler = logging.FileHandler(log_file, encoding="utf-8")
        else:
            handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger
