"""Unit tests for Priority 9.2 additions to agent.core.roamin_logging."""

from __future__ import annotations

import json
import logging
import time
from io import StringIO

from agent.core.roamin_logging import (
    JsonFormatter,
    ThrottledLogger,
    bind_request_id,
    get_json_logger,
    get_request_id,
    set_request_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_logger(name: str) -> tuple[logging.Logger, StringIO]:
    """Return a logger + StringIO stream wired with JsonFormatter."""
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger(name)
    log.handlers.clear()
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    log.propagate = False
    return log, buf


# ---------------------------------------------------------------------------
# 9.2.1 — JsonFormatter
# ---------------------------------------------------------------------------


def test_json_formatter_required_fields():
    """JsonFormatter output is valid JSON with timestamp, level, logger, message."""
    log, buf = _capture_logger("test.json.required")
    set_request_id(None)  # ensure clean state
    log.info("hello world")
    line = buf.getvalue().strip()
    data = json.loads(line)
    assert "timestamp" in data
    assert data["level"] == "INFO"
    assert data["logger"] == "test.json.required"
    assert data["message"] == "hello world"


def test_json_formatter_includes_request_id():
    """JsonFormatter includes request_id when set via set_request_id()."""
    log, buf = _capture_logger("test.json.rid")
    set_request_id("req-abc-123")
    try:
        log.info("with request id")
        data = json.loads(buf.getvalue().strip())
        assert data["request_id"] == "req-abc-123"
    finally:
        set_request_id(None)


def test_json_formatter_omits_request_id_when_not_set():
    """JsonFormatter does NOT include request_id key when not set."""
    log, buf = _capture_logger("test.json.norid")
    set_request_id(None)
    log.info("no request id")
    data = json.loads(buf.getvalue().strip())
    assert "request_id" not in data


# ---------------------------------------------------------------------------
# 9.2.2 — ThrottledLogger
# ---------------------------------------------------------------------------


def test_throttled_logger_emits_first_message():
    """ThrottledLogger emits the first occurrence of a message immediately."""
    inner = logging.getLogger("test.throttle.first")
    inner.handlers.clear()
    buf = StringIO()
    inner.addHandler(logging.StreamHandler(buf))
    inner.setLevel(logging.DEBUG)
    inner.propagate = False

    tl = ThrottledLogger(inner, cooldown_seconds=60)
    tl.info("first message")
    assert "first message" in buf.getvalue()


def test_throttled_logger_suppresses_duplicate_within_cooldown():
    """ThrottledLogger suppresses the same message within the cooldown window."""
    inner = logging.getLogger("test.throttle.suppress")
    inner.handlers.clear()
    buf = StringIO()
    inner.addHandler(logging.StreamHandler(buf))
    inner.setLevel(logging.DEBUG)
    inner.propagate = False

    tl = ThrottledLogger(inner, cooldown_seconds=60)
    tl.info("repeated msg")
    buf.truncate(0)
    buf.seek(0)
    tl.info("repeated msg")  # should be suppressed
    assert buf.getvalue() == ""


def test_throttled_logger_emits_after_cooldown_expires():
    """ThrottledLogger re-emits after the cooldown expires."""
    inner = logging.getLogger("test.throttle.expire")
    inner.handlers.clear()
    buf = StringIO()
    inner.addHandler(logging.StreamHandler(buf))
    inner.setLevel(logging.DEBUG)
    inner.propagate = False

    tl = ThrottledLogger(inner, cooldown_seconds=0.01)
    tl.info("timed msg")
    buf.truncate(0)
    buf.seek(0)
    time.sleep(0.02)
    tl.info("timed msg")  # cooldown expired — should re-emit
    assert "timed msg" in buf.getvalue()


def test_throttled_logger_flush_emits_suppressed_count():
    """ThrottledLogger.flush() emits a suppression summary if messages were dropped."""
    inner = logging.getLogger("test.throttle.flush")
    inner.handlers.clear()
    buf = StringIO()
    inner.addHandler(logging.StreamHandler(buf))
    inner.setLevel(logging.DEBUG)
    inner.propagate = False

    tl = ThrottledLogger(inner, cooldown_seconds=60)
    tl.info("spam msg")
    tl.info("spam msg")
    tl.info("spam msg")
    buf.truncate(0)
    buf.seek(0)
    tl.flush()
    output = buf.getvalue()
    assert "suppressed" in output
    assert "2" in output  # 2 duplicates suppressed


# ---------------------------------------------------------------------------
# 9.2.3 — bind_request_id context manager
# ---------------------------------------------------------------------------


def test_bind_request_id_restores_previous_on_exit():
    """bind_request_id restores the previous request_id when the block exits."""
    set_request_id("outer")
    with bind_request_id("inner"):
        assert get_request_id() == "inner"
    assert get_request_id() == "outer"


# ---------------------------------------------------------------------------
# 9.2.4 — get_json_logger factory
# ---------------------------------------------------------------------------


def test_get_json_logger_uses_json_formatter():
    """get_json_logger() returns a logger whose handler uses JsonFormatter."""
    log = get_json_logger("test.factory.json")
    assert any(isinstance(h.formatter, JsonFormatter) for h in log.handlers)
