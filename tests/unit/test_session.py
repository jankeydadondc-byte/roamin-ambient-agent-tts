"""Tests for SessionTranscript — conversation continuity (Priority 11.6)."""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from agent.core.voice.session import SessionTranscript

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(max_exchanges=10, timeout_min=30, db_path=None) -> SessionTranscript:
    """Create a fresh SessionTranscript with optional in-memory DB."""
    if db_path is None:
        # Use a temp file so tests don't touch the real DB
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
    return SessionTranscript(
        max_exchanges=max_exchanges,
        session_timeout_minutes=timeout_min,
        db_path=db_path,
    )


# ---------------------------------------------------------------------------
# Ring buffer tests
# ---------------------------------------------------------------------------


class TestRingBuffer:
    def test_add_and_retrieve(self):
        s = _make_session()
        s.add("user", "Hello")
        s.add("assistant", "Hey bud")
        assert s.exchange_count == 2

    def test_buffer_overflow(self):
        """Buffer should discard oldest when full."""
        s = _make_session(max_exchanges=3)
        for i in range(5):
            s.add("user", f"msg {i}")
        assert s.exchange_count == 3
        exchanges = s.get_exchanges()
        # Should have the last 3 messages
        assert exchanges[0]["text"] == "msg 2"
        assert exchanges[2]["text"] == "msg 4"

    def test_invalid_role_raises(self):
        s = _make_session()
        with pytest.raises(ValueError, match="role must be"):
            s.add("system", "bad role")

    def test_empty_session(self):
        s = _make_session()
        assert s.is_empty
        assert s.exchange_count == 0


# ---------------------------------------------------------------------------
# Context block formatting
# ---------------------------------------------------------------------------


class TestContextBlock:
    def test_empty_returns_empty_string(self):
        s = _make_session()
        assert s.get_context_block() == ""

    def test_format(self):
        s = _make_session()
        s.add("user", "What's the weather?")
        s.add("assistant", "Looks like rain, bud.")
        block = s.get_context_block()
        assert "## Conversation So Far" in block
        assert "Asherre: What's the weather?" in block
        assert "Roamin: Looks like rain, bud." in block

    def test_format_preserves_order(self):
        s = _make_session()
        s.add("user", "First")
        s.add("assistant", "Reply 1")
        s.add("user", "Second")
        s.add("assistant", "Reply 2")
        block = s.get_context_block()
        lines = block.split("\n")
        # Header + 4 exchanges
        assert len(lines) == 5
        assert lines[1] == "Asherre: First"
        assert lines[4] == "Roamin: Reply 2"


# ---------------------------------------------------------------------------
# Session timeout
# ---------------------------------------------------------------------------


class TestSessionTimeout:
    def test_auto_new_session_on_timeout(self):
        s = _make_session(timeout_min=1)  # 1 minute timeout
        s.add("user", "Hello")
        old_id = s.session_id
        # Force timeout by setting last activity far in the past
        s._last_activity = time.time() - 120  # 2 minutes ago
        s.add("user", "After timeout")
        # Buffer should only have the new message (old ones cleared on rotate)
        assert s.exchange_count == 1
        assert s.session_id != old_id

    def test_no_timeout_within_window(self):
        s = _make_session(timeout_min=60)  # 60 minutes
        s.add("user", "Hello")
        old_id = s.session_id
        s.add("user", "Still here")
        assert s.session_id == old_id
        assert s.exchange_count == 2

    def test_timeout_disabled_when_zero_seconds(self):
        """timeout_min=0 means 0 seconds, which should always timeout."""
        s = _make_session(timeout_min=0)
        s._session_timeout_seconds = 0  # Explicitly disable
        s.add("user", "Hello")
        old_id = s.session_id
        s.add("user", "Same session")
        # With 0 seconds timeout, _is_timed_out returns False (disabled)
        assert s.session_id == old_id


# ---------------------------------------------------------------------------
# Manual reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_buffer(self):
        s = _make_session()
        s.add("user", "Hello")
        s.add("assistant", "Hey")
        old_id = s.session_id
        new_id = s.reset(reason="voice_command")
        assert s.is_empty
        assert new_id != old_id
        assert s.session_id == new_id

    def test_reset_returns_new_id(self):
        s = _make_session()
        id1 = s.session_id
        id2 = s.reset()
        id3 = s.reset()
        assert id1 != id2
        assert id2 != id3


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_persist_to_sqlite(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        s = _make_session(db_path=db_path)
        s.add("user", "Test message")
        s.add("assistant", "Test reply")

        # Read back from DB
        history = s.get_history(limit=10)
        assert len(history) >= 2
        # Most recent should have our content
        contents = [h["content"] for h in history]
        assert any("Test message" in c for c in contents)
        assert any("Test reply" in c for c in contents)

    def test_history_filters_by_session(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        s = _make_session(db_path=db_path)
        s.add("user", "Session 1 message")
        session1_id = s.session_id
        s.reset(reason="test")
        s.add("user", "Session 2 message")

        # Session 1 history
        h1 = s.get_history(session_id=session1_id)
        assert len(h1) == 1
        assert "Session 1" in h1[0]["content"]

        # Session 2 (current) history
        h2 = s.get_history()
        assert len(h2) == 1
        assert "Session 2" in h2[0]["content"]


# ---------------------------------------------------------------------------
# get_exchanges serialization
# ---------------------------------------------------------------------------


class TestGetExchanges:
    def test_returns_dicts(self):
        s = _make_session()
        s.add("user", "Hello")
        s.add("assistant", "Hey")
        exchanges = s.get_exchanges()
        assert isinstance(exchanges, list)
        assert len(exchanges) == 2
        assert exchanges[0]["role"] == "user"
        assert exchanges[0]["text"] == "Hello"
        assert "timestamp" in exchanges[0]

    def test_limit(self):
        s = _make_session()
        for i in range(5):
            s.add("user", f"msg {i}")
        limited = s.get_exchanges(limit=2)
        assert len(limited) == 2
        assert limited[0]["text"] == "msg 3"
        assert limited[1]["text"] == "msg 4"


# ---------------------------------------------------------------------------
# Session ID format
# ---------------------------------------------------------------------------


class TestSessionId:
    def test_session_id_format(self):
        s = _make_session()
        assert s.session_id.startswith("session_")
        assert len(s.session_id) == len("session_") + 12

    def test_unique_ids(self):
        ids = set()
        for _ in range(20):
            s = _make_session()
            ids.add(s.session_id)
        assert len(ids) == 20
