"""Tests for HITL approval flow — blocked step persistence and API endpoints."""

import tempfile
from unittest.mock import MagicMock, patch

from agent.core.memory.memory_store import MemoryStore


class TestPendingApprovalCRUD:
    """Verify pending_approvals table create/read/resolve operations."""

    def _make_store(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        return MemoryStore(db_path=tmp.name)

    def test_create_returns_id(self):
        store = self._make_store()
        aid = store.create_pending_approval(None, 1, "write_file", "Write summary", None)
        assert isinstance(aid, int)
        assert aid > 0

    def test_get_pending_approval(self):
        store = self._make_store()
        aid = store.create_pending_approval(42, 3, "delete_file", "Delete old log", '{"path":"x"}', "high")
        record = store.get_pending_approval(aid)
        assert record is not None
        assert record["status"] == "pending"
        assert record["tool"] == "delete_file"
        assert record["action"] == "Delete old log"
        assert record["task_run_id"] == 42
        assert record["step_number"] == 3

    def test_resolve_approved(self):
        store = self._make_store()
        aid = store.create_pending_approval(None, 1, "write_file", "Write note", None)
        result = store.resolve_approval(aid, "approved")
        assert result is True
        record = store.get_pending_approval(aid)
        assert record["status"] == "approved"
        assert record["resolved_at"] is not None

    def test_resolve_denied(self):
        store = self._make_store()
        aid = store.create_pending_approval(None, 1, "write_file", "Write note", None)
        store.resolve_approval(aid, "denied")
        record = store.get_pending_approval(aid)
        assert record["status"] == "denied"

    def test_get_pending_approvals_filters_resolved(self):
        store = self._make_store()
        aid1 = store.create_pending_approval(None, 1, "write_file", "Action A", None)
        aid2 = store.create_pending_approval(None, 2, "delete_file", "Action B", None)
        store.resolve_approval(aid1, "approved")
        pending = store.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["id"] == aid2

    def test_get_nonexistent_returns_none(self):
        store = self._make_store()
        assert store.get_pending_approval(9999) is None


class TestHandleBlockedSteps:
    """Verify _handle_blocked_steps stores and toasts blocked steps."""

    @patch("agent.core.voice.wake_listener._notify_approval_toast")
    def test_toast_called_for_each_blocked_step(self, mock_toast):
        from agent.core.voice.wake_listener import _handle_blocked_steps

        mock_memory = MagicMock()
        mock_memory.store_pending_approval.return_value = 7

        blocked = [
            {"step": 2, "tool": "write_file", "action": "Write note", "risk": "high"},
            {"step": 3, "tool": "delete_file", "action": "Delete file", "risk": "high"},
        ]
        _handle_blocked_steps(blocked, mock_memory)

        assert mock_memory.store_pending_approval.call_count == 2
        assert mock_toast.call_count == 2

    @patch("agent.core.voice.wake_listener._notify_approval_toast")
    def test_empty_blocked_steps_is_noop(self, mock_toast):
        from agent.core.voice.wake_listener import _handle_blocked_steps

        mock_memory = MagicMock()
        _handle_blocked_steps([], mock_memory)
        mock_memory.store_pending_approval.assert_not_called()
        mock_toast.assert_not_called()

    @patch("agent.core.voice.wake_listener._notify_approval_toast", side_effect=RuntimeError("toast failed"))
    def test_toast_failure_does_not_raise(self, _mock_toast):
        from agent.core.voice.wake_listener import _handle_blocked_steps

        mock_memory = MagicMock()
        mock_memory.store_pending_approval.return_value = 1
        # Should not raise
        _handle_blocked_steps([{"step": 1, "tool": "write_file", "action": "A", "risk": "high"}], mock_memory)


class TestApprovalAPIEndpoints:
    """Verify /approve, /deny, and /pending-approvals Control API endpoints."""

    def _client_with_store(self, store: MemoryStore):
        from fastapi.testclient import TestClient

        from agent.control_api import app

        with TestClient(app) as client:
            with (
                patch("agent.control_api.MemoryStore", return_value=store),
                patch("agent.core.memory.memory_store.MemoryStore", return_value=store),
            ):
                yield client

    def test_pending_approvals_empty(self):
        from fastapi.testclient import TestClient

        from agent.control_api import app

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        store = MemoryStore(db_path=tmp.name)

        with patch("agent.core.memory.memory_store.MemoryStore", return_value=store):
            with TestClient(app) as client:
                resp = client.get("/pending-approvals")
                assert resp.status_code == 200
                assert resp.json()["approvals"] == []

    def test_deny_endpoint_resolves_denied(self):
        from fastapi.testclient import TestClient

        from agent.control_api import app

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        store = MemoryStore(db_path=tmp.name)
        aid = store.create_pending_approval(None, 1, "write_file", "Write note", None)

        with patch("agent.core.memory.memory_store.MemoryStore", return_value=store):
            with TestClient(app) as client:
                resp = client.get(f"/deny/{aid}")
                assert resp.status_code == 200
                assert "denied" in resp.text.lower()

        record = store.get_pending_approval(aid)
        assert record["status"] == "denied"

    def test_approve_endpoint_executes_tool(self):
        from fastapi.testclient import TestClient

        from agent.control_api import app

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        store = MemoryStore(db_path=tmp.name)
        aid = store.create_pending_approval(None, 1, "notify", "Say hello", '{"message":"hello","title":"Test"}')

        mock_registry = MagicMock()
        mock_registry.execute.return_value = {"result": "notified"}

        with (
            patch("agent.core.memory.memory_store.MemoryStore", return_value=store),
            patch("agent.core.tool_registry.ToolRegistry", return_value=mock_registry),
            patch("agent.core.screen_observer._notify_windows"),
        ):
            with TestClient(app) as client:
                resp = client.get(f"/approve/{aid}")
                assert resp.status_code == 200
                assert "approved" in resp.text.lower()

        record = store.get_pending_approval(aid)
        assert record["status"] == "approved"

    def test_approve_nonexistent_returns_404(self):
        from fastapi.testclient import TestClient

        from agent.control_api import app

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        store = MemoryStore(db_path=tmp.name)

        with patch("agent.core.memory.memory_store.MemoryStore", return_value=store):
            with TestClient(app) as client:
                resp = client.get("/approve/9999")
                assert resp.status_code == 404
