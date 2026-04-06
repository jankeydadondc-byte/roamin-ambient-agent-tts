"""Tests for 6.3 — Persistent Task History."""

import tempfile
from unittest.mock import MagicMock, patch

from agent.core.memory.memory_store import MemoryStore


class TestTaskRunCRUD:
    """Verify task_runs table create/read/finish operations."""

    def _make_store(self):
        """Create MemoryStore with a temp database."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        return MemoryStore(db_path=tmp.name)

    def test_create_task_run_returns_id(self):
        store = self._make_store()
        run_id = store.create_task_run("search for python tips", "default")
        assert isinstance(run_id, int)
        assert run_id > 0

    def test_finish_task_run_updates_status(self):
        store = self._make_store()
        run_id = store.create_task_run("test goal", "default")
        store.finish_task_run(run_id, "completed", 3)
        runs = store.get_task_runs()
        assert len(runs) == 1
        assert runs[0]["status"] == "completed"
        assert runs[0]["step_count"] == 3
        assert runs[0]["finished_at"] is not None

    def test_failed_task_recorded(self):
        store = self._make_store()
        run_id = store.create_task_run("bad goal", "default")
        store.finish_task_run(run_id, "failed", 0)
        runs = store.get_task_runs()
        assert runs[0]["status"] == "failed"
        assert runs[0]["step_count"] == 0

    def test_cancelled_task_recorded(self):
        store = self._make_store()
        run_id = store.create_task_run("cancelled goal", "default")
        store.finish_task_run(run_id, "cancelled", 2)
        runs = store.get_task_runs()
        assert runs[0]["status"] == "cancelled"


class TestTaskStepCRUD:
    """Verify task_steps table operations."""

    def _make_store(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        return MemoryStore(db_path=tmp.name)

    def test_add_and_get_steps(self):
        store = self._make_store()
        run_id = store.create_task_run("goal", "default")
        store.add_task_step(run_id, 1, "web_search", "Search web", '{"query":"test"}', "results", "executed", 150)
        store.add_task_step(run_id, 2, "notify", "Notify user", '{"message":"done"}', "sent", "executed", 50)
        steps = store.get_task_steps(run_id)
        assert len(steps) == 2
        assert steps[0]["step_number"] == 1
        assert steps[0]["tool"] == "web_search"
        assert steps[0]["duration_ms"] == 150
        assert steps[1]["step_number"] == 2

    def test_steps_linked_to_correct_run(self):
        store = self._make_store()
        run1 = store.create_task_run("goal1", "default")
        run2 = store.create_task_run("goal2", "default")
        store.add_task_step(run1, 1, "notify", "A", None, None, "executed")
        store.add_task_step(run2, 1, "web_search", "B", None, None, "executed")
        assert len(store.get_task_steps(run1)) == 1
        assert len(store.get_task_steps(run2)) == 1
        assert store.get_task_steps(run1)[0]["tool"] == "notify"
        assert store.get_task_steps(run2)[0]["tool"] == "web_search"


class TestTaskRunQueries:
    """Verify filtering and search queries."""

    def _make_store(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        return MemoryStore(db_path=tmp.name)

    def test_filter_by_status(self):
        store = self._make_store()
        r1 = store.create_task_run("goal1", "default")
        r2 = store.create_task_run("goal2", "default")
        store.finish_task_run(r1, "completed", 1)
        store.finish_task_run(r2, "failed", 0)
        completed = store.get_task_runs(status="completed")
        assert len(completed) == 1
        assert completed[0]["goal"] == "goal1"

    def test_search_by_goal_keyword(self):
        store = self._make_store()
        store.create_task_run("search for python tips", "default")
        store.create_task_run("open browser", "default")
        results = store.search_task_history("python")
        assert len(results) == 1
        assert "python" in results[0]["goal"]

    def test_search_by_step_action_keyword(self):
        store = self._make_store()
        run_id = store.create_task_run("do stuff", "default")
        store.add_task_step(run_id, 1, "web_search", "Search DuckDuckGo", None, None, "executed")
        results = store.search_task_history("DuckDuckGo")
        assert len(results) == 1
        assert results[0]["goal"] == "do stuff"

    def test_limit_respected(self):
        store = self._make_store()
        for i in range(10):
            store.create_task_run(f"goal {i}", "default")
        runs = store.get_task_runs(limit=3)
        assert len(runs) == 3

    def test_empty_result(self):
        store = self._make_store()
        runs = store.get_task_runs()
        assert runs == []


class TestAgentLoopTaskHistoryIntegration:
    """Verify AgentLoop.run() creates task history records."""

    @patch("agent.core.agent_loop.AgentLoop._generate_plan")
    @patch("agent.core.agent_loop.AgentLoop._execute_step")
    @patch("agent.core.agent_loop.AgentLoop._classify_task", return_value="default")
    @patch("agent.core.agent_loop.AgentLoop.__init__", return_value=None)
    def test_task_run_created_after_execution(self, _init, _classify, mock_exec, mock_plan):
        """After AgentLoop.run(), a task_runs row exists."""
        from agent.core.agent_loop import AgentLoop

        loop = AgentLoop.__new__(AgentLoop)
        loop._cancel_event = MagicMock()
        loop._cancel_event.is_set.return_value = False
        loop._cancel_event.clear = MagicMock()
        loop._context_builder = MagicMock()
        loop._context_builder.build.return_value = "ctx"

        # Use a real MemoryManager with temp db
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        from agent.core.memory.memory_manager import MemoryManager

        mm = MemoryManager()
        mm.store = MemoryStore(db_path=tmp.name)
        loop._memory = mm

        mock_plan.return_value = [
            {"step": 1, "action": "Do thing", "tool": "notify", "params": {"message": "hi"}, "risk": "low"},
        ]
        mock_exec.return_value = {"status": "executed", "outcome": "ok"}

        result = loop.run("test task history")
        assert result["status"] == "completed"

        runs = mm.store.get_task_runs()
        assert len(runs) == 1
        assert runs[0]["goal"] == "test task history"
        assert runs[0]["status"] == "completed"
        assert runs[0]["step_count"] == 1

        steps = mm.store.get_task_steps(runs[0]["id"])
        assert len(steps) == 1
        assert steps[0]["tool"] == "notify"
        assert steps[0]["duration_ms"] is not None


class TestTaskHistoryNonFatal:
    """Verify logging failure does not abort task execution."""

    @patch("agent.core.agent_loop.AgentLoop._generate_plan")
    @patch("agent.core.agent_loop.AgentLoop._execute_step")
    @patch("agent.core.agent_loop.AgentLoop._classify_task", return_value="default")
    @patch("agent.core.agent_loop.AgentLoop.__init__", return_value=None)
    def test_broken_memory_does_not_crash(self, _init, _classify, mock_exec, mock_plan):
        """If memory raises on task logging, the task still completes."""
        from agent.core.agent_loop import AgentLoop

        loop = AgentLoop.__new__(AgentLoop)
        loop._cancel_event = MagicMock()
        loop._cancel_event.is_set.return_value = False
        loop._cancel_event.clear = MagicMock()
        loop._context_builder = MagicMock()
        loop._context_builder.build.return_value = "ctx"

        # Memory that raises on everything
        mock_memory = MagicMock()
        mock_memory.start_task.side_effect = RuntimeError("db locked")
        mock_memory.write_to_memory.side_effect = RuntimeError("db locked")
        loop._memory = mock_memory

        mock_plan.return_value = [
            {"step": 1, "action": "A", "tool": "notify", "params": {}, "risk": "low"},
        ]
        mock_exec.return_value = {"status": "executed", "outcome": "ok"}

        # Should NOT raise
        result = loop.run("test goal")
        assert result["status"] == "completed"


class TestTaskHistoryAPI:
    """Verify /task-history endpoint with persistent data."""

    def test_task_history_endpoint_returns_tasks(self):
        """GET /task-history returns task data."""
        from fastapi.testclient import TestClient

        from agent.control_api import app

        with TestClient(app) as client:
            resp = client.get("/task-history")
            assert resp.status_code == 200
            data = resp.json()
            assert "tasks" in data
