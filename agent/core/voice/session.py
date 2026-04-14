"""Conversation session transcript — ring buffer with SQLite persistence.

Maintains the last N exchanges (user + assistant pairs) for context injection
into the model prompt. Supports session timeout (auto-new-session after
configurable inactivity), voice command reset, and persistence to the
existing conversation_history SQLite table.

Part of Priority 11.6 — Conversation Continuity.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from threading import Lock

logger = logging.getLogger(__name__)

# Defaults — overridable via env vars
_DEFAULT_MAX_EXCHANGES = 10
_DEFAULT_SESSION_TIMEOUT_MIN = int(os.environ.get("ROAMIN_SESSION_TIMEOUT_MIN", "30"))


@dataclass
class Exchange:
    """A single user/assistant exchange pair."""

    role: str  # "user" or "assistant"
    text: str
    timestamp: float = field(default_factory=time.time)


class SessionTranscript:
    """Ring buffer of recent conversation exchanges with SQLite persistence.

    Thread-safe. Designed as a singleton per process — one active session at a
    time, with automatic rotation after inactivity.

    Usage:
        session = SessionTranscript()
        session.add("user", "What's the weather?")
        session.add("assistant", "Looks like rain, bud.")
        context = session.get_context_block()
    """

    def __init__(
        self,
        max_exchanges: int = _DEFAULT_MAX_EXCHANGES,
        session_timeout_minutes: int = _DEFAULT_SESSION_TIMEOUT_MIN,
        db_path: str | None = None,
    ) -> None:
        self._max_exchanges = max_exchanges
        self._session_timeout_seconds = session_timeout_minutes * 60
        self._buffer: deque[Exchange] = deque(maxlen=max_exchanges)
        self._lock = Lock()
        self._session_id = self._new_session_id()
        self._last_activity: float = time.time()

        # Lazy-import MemoryStore to avoid circular imports at module level
        self._db_path = db_path
        self._memory_store = None  # lazy init

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        """Current session identifier."""
        return self._session_id

    def add(self, role: str, text: str) -> None:
        """Append a user or assistant message to the session buffer.

        If the session has timed out since the last activity, a new session
        is started automatically before appending.
        """
        if role not in ("user", "assistant"):
            raise ValueError(f"role must be 'user' or 'assistant', got '{role}'")

        with self._lock:
            # Auto-rotate session on timeout
            if self._is_timed_out():
                logger.info(
                    "Session %s timed out after %d min of inactivity — starting new session",
                    self._session_id,
                    self._session_timeout_seconds // 60,
                )
                self._rotate_session()

            exchange = Exchange(role=role, text=text)
            self._buffer.append(exchange)
            self._last_activity = time.time()

        # Persist to SQLite (outside lock — DB has its own locking)
        self._persist(role, text)

    def get_context_block(self) -> str:
        """Format the current session buffer as a prompt-injectable context block.

        Returns an empty string if the buffer is empty.

        Format:
            ## Conversation So Far
            User: What's the weather?
            Roamin: Looks like rain, bud.
        """
        with self._lock:
            if not self._buffer:
                return ""

            lines = ["## Conversation So Far"]
            for ex in self._buffer:
                label = "Asherre" if ex.role == "user" else "Roamin"
                lines.append(f"{label}: {ex.text}")

            return "\n".join(lines)

    def reset(self, reason: str = "manual") -> str:
        """Start a new session, clearing the buffer. Returns the new session_id.

        Args:
            reason: Why the session was reset (for logging). Common values:
                    "manual", "voice_command", "timeout"
        """
        with self._lock:
            old_id = self._session_id
            self._rotate_session()
            logger.info("Session reset (%s): %s -> %s", reason, old_id, self._session_id)
        return self._session_id

    def get_exchanges(self, limit: int | None = None) -> list[dict]:
        """Return exchanges as a list of dicts for API serialization.

        Args:
            limit: Max number of exchanges to return (most recent). None = all.
        """
        with self._lock:
            items = list(self._buffer)
            if limit is not None:
                items = items[-limit:]
            return [
                {
                    "role": ex.role,
                    "text": ex.text,
                    "timestamp": ex.timestamp,
                }
                for ex in items
            ]

    def get_history(
        self,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Fetch persisted conversation history from SQLite.

        This reads from the database, not the in-memory buffer, so it can
        return history from previous sessions.

        Args:
            session_id: Filter by session. None = current session.
            limit: Max rows to return.
            offset: Pagination offset.
        """
        store = self._get_store()
        if store is None:
            return []

        sid = session_id or self._session_id
        try:
            rows = store.get_conversation_history(session_id=sid)
            # Apply pagination manually (MemoryStore doesn't support limit/offset on this query)
            return rows[offset : offset + limit]
        except Exception as e:
            logger.warning("Failed to fetch chat history: %s", e)
            return []

    @property
    def is_empty(self) -> bool:
        """True if the current session buffer has no exchanges."""
        with self._lock:
            return len(self._buffer) == 0

    @property
    def exchange_count(self) -> int:
        """Number of exchanges currently in the buffer."""
        with self._lock:
            return len(self._buffer)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _is_timed_out(self) -> bool:
        """Check if the session has been inactive beyond the timeout threshold."""
        if self._session_timeout_seconds <= 0:
            return False  # timeout disabled
        elapsed = time.time() - self._last_activity
        return elapsed > self._session_timeout_seconds

    def _rotate_session(self) -> None:
        """Clear buffer and generate a new session ID. Caller must hold _lock."""
        self._buffer.clear()
        self._session_id = self._new_session_id()
        self._last_activity = time.time()

    @staticmethod
    def _new_session_id() -> str:
        """Generate a new unique session identifier."""
        return f"session_{uuid.uuid4().hex[:12]}"

    def _get_store(self):
        """Lazy-load MemoryStore to avoid import-time side effects."""
        if self._memory_store is None:
            try:
                from agent.core.memory.memory_store import MemoryStore

                self._memory_store = MemoryStore(db_path=self._db_path)
            except Exception as e:
                logger.warning("Could not initialize MemoryStore for session persistence: %s", e)
                return None
        return self._memory_store

    def _persist(self, role: str, text: str) -> None:
        """Write an exchange to the conversation_history table."""
        store = self._get_store()
        if store is None:
            return
        try:
            content = f"{'Asherre' if role == 'user' else 'Roamin'}: {text}"
            store.add_conversation_history(
                session_id=self._session_id,
                model_used="session",  # marker — model is recorded elsewhere
                content=content,
            )
        except Exception as e:
            logger.warning("Failed to persist exchange: %s", e)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_session_instance: SessionTranscript | None = None
_session_lock = Lock()


def get_session() -> SessionTranscript:
    """Return the global SessionTranscript singleton.

    Thread-safe. Creates the instance on first call.
    """
    global _session_instance
    if _session_instance is not None:
        return _session_instance
    with _session_lock:
        if _session_instance is None:
            _session_instance = SessionTranscript()
    return _session_instance
