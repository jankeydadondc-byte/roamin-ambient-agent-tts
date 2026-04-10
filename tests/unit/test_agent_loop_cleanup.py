"""Unit tests for AgentLoop._cleanup_completed_tasks() and _should_throttle() — 9.1.2."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

from agent.core.agent_loop import AgentLoop

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loop() -> AgentLoop:
    """Return an AgentLoop with all heavy __init__ deps mocked out."""
    with (
        patch("agent.core.agent_loop.MemoryManager"),
        patch("agent.core.agent_loop.ModelRouter"),
        patch("agent.core.agent_loop.ContextBuilder"),
        patch("agent.core.agent_loop.ToolRegistry"),
    ):
        return AgentLoop()


def _in_memory_conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the task_runs schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE task_runs (
            id INTEGER PRIMARY KEY,
            goal TEXT,
            status TEXT,
            started_at TEXT
        )
        """
    )
    conn.commit()
    return conn


def _insert(conn: sqlite3.Connection, status: str, hours_ago: float) -> None:
    ts = (datetime.now() - timedelta(hours=hours_ago)).isoformat()
    conn.execute(
        "INSERT INTO task_runs (goal, status, started_at) VALUES (?, ?, ?)",
        ("goal", status, ts),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# _cleanup_completed_tasks
# ---------------------------------------------------------------------------


def test_cleanup_empty_db_returns_zero():
    """Returns deleted_count=0 when no rows exist."""
    conn = _in_memory_conn()
    loop = _make_loop()

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("sqlite3.connect", return_value=conn),
    ):
        result = loop._cleanup_completed_tasks(older_than_hours=24)

    assert result["deleted_count"] == 0
    assert result["oldest_retained_ts"] is None


def test_cleanup_deletes_old_completed_tasks():
    """Deletes completed rows older than cutoff; deleted_count reflects rows removed."""
    conn = _in_memory_conn()
    _insert(conn, "completed", hours_ago=48)
    _insert(conn, "completed", hours_ago=48)
    loop = _make_loop()

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("sqlite3.connect", return_value=conn),
    ):
        result = loop._cleanup_completed_tasks(older_than_hours=24)

    # deleted_count is the authoritative return value; conn is closed by the function
    assert result["deleted_count"] == 2


def test_cleanup_keeps_recent_completed_tasks():
    """Leaves completed rows younger than cutoff; deleted_count is 0."""
    conn = _in_memory_conn()
    _insert(conn, "completed", hours_ago=1)
    loop = _make_loop()

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("sqlite3.connect", return_value=conn),
    ):
        result = loop._cleanup_completed_tasks(older_than_hours=24)

    assert result["deleted_count"] == 0


def test_cleanup_keeps_running_tasks_regardless_of_age():
    """Never deletes running tasks; deleted_count is 0 even for very old rows."""
    conn = _in_memory_conn()
    _insert(conn, "running", hours_ago=100)
    loop = _make_loop()

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("sqlite3.connect", return_value=conn),
    ):
        result = loop._cleanup_completed_tasks(older_than_hours=24)

    assert result["deleted_count"] == 0


def test_cleanup_returns_zero_when_db_missing():
    """Returns deleted_count=0 immediately when the database file does not exist."""
    loop = _make_loop()

    with patch("pathlib.Path.exists", return_value=False):
        result = loop._cleanup_completed_tasks(older_than_hours=24)

    assert result == {"deleted_count": 0, "oldest_retained_ts": None}


# ---------------------------------------------------------------------------
# _should_throttle
# ---------------------------------------------------------------------------


def test_should_throttle_returns_false_on_exception():
    """_should_throttle() returns False (fail-open) when is_resource_exhausted raises."""
    loop = _make_loop()
    with patch("agent.core.resource_monitor.is_resource_exhausted", side_effect=RuntimeError("boom")):
        result = loop._should_throttle()
    assert result is False


def test_should_throttle_returns_true_when_exhausted():
    """_should_throttle() returns True when is_resource_exhausted() returns True."""
    loop = _make_loop()
    with patch("agent.core.resource_monitor.is_resource_exhausted", return_value=True):
        result = loop._should_throttle()
    assert result is True
