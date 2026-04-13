"""tests/test_agent_loop.py — unit tests for AgentLoop.

Covers:
  - Status accuracy (#7): failed / partial / completed / blocked
  - Executor non-blocking shutdown on timeout (#6)
  - _execute_step behaviour for null-tool, unknown-tool, and tool error paths
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_loop():
    """Return an AgentLoop with all heavy dependencies mocked out."""
    with (
        patch("agent.core.agent_loop.MemoryManager"),
        patch("agent.core.agent_loop.ModelRouter"),
        patch("agent.core.agent_loop.ContextBuilder"),
        patch("agent.core.agent_loop.ToolRegistry"),
        patch("agent.core.agent_loop.ScreenObserver"),
    ):
        from agent.core.agent_loop import AgentLoop

        loop = AgentLoop()
    return loop


# ---------------------------------------------------------------------------
# Status accuracy tests (#7)
# ---------------------------------------------------------------------------


class TestAgentLoopStatus:
    def test_all_steps_failed_marks_failed(self, mock_loop):
        """All steps failing must yield status='failed', not 'completed' (#7)."""
        # Simulate planner returning one step, executor failing it
        mock_loop._router.respond.return_value = (
            '[{"step":1,"action":"do it","tool":"bad_tool","params":{},"risk":"low"}]'
        )
        mock_loop._registry.get.return_value = MagicMock()  # tool exists
        mock_loop._registry.execute.side_effect = RuntimeError("tool exploded")
        mock_loop._registry.get_risk_level.return_value = "low"
        mock_loop._context_builder.build.return_value = ""
        mock_loop._memory.store.begin_task_run.return_value = 1
        mock_loop._memory.store.finish_task.return_value = None
        mock_loop._memory.store.add_task_step.return_value = None

        result = mock_loop.run("do something")
        assert result["status"] == "failed"

    def test_no_steps_marks_blocked(self, mock_loop):
        """Planner returning no steps must yield status='blocked' (#7)."""
        # Return empty JSON array from model
        mock_loop._router.respond.return_value = "[]"
        mock_loop._context_builder.build.return_value = ""
        mock_loop._memory.store.begin_task_run.return_value = 1
        mock_loop._memory.store.finish_task.return_value = None

        result = mock_loop.run("do nothing")
        assert result["status"] == "blocked"

    def test_successful_step_marks_completed(self, mock_loop):
        """All steps succeeding must yield status='completed' (#7)."""
        mock_loop._router.respond.return_value = (
            '[{"step":1,"action":"do it","tool":"good_tool","params":{},"risk":"low"}]'
        )
        mock_loop._registry.get.return_value = MagicMock()
        mock_loop._registry.execute.return_value = {"result": "ok"}
        mock_loop._registry.get_risk_level.return_value = "low"
        mock_loop._context_builder.build.return_value = ""
        mock_loop._memory.store.begin_task_run.return_value = 1
        mock_loop._memory.store.finish_task.return_value = None
        mock_loop._memory.store.add_task_step.return_value = None

        result = mock_loop.run("do something good")
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# Executor timeout non-blocking test (#6)
# ---------------------------------------------------------------------------


class TestExecutorTimeout:
    def test_timeout_does_not_block_caller(self, mock_loop):
        """After TimeoutError, executor shutdown must not block for another full timeout (#6)."""

        def slow_tool(*args, **kwargs):
            time.sleep(60)

        mock_loop._registry.execute.side_effect = slow_tool
        mock_loop._registry.get_risk_level.return_value = "low"
        mock_loop._registry.get.return_value = MagicMock()

        step = {
            "step": 1,
            "action": "slow action",
            "tool": "slow_tool",
            "params": {},
            "risk": "low",
        }

        with patch("agent.core.agent_loop._TOOL_TIMEOUT_SECONDS", 0.1):
            start = time.time()
            result = mock_loop._execute_step(step)
            elapsed = time.time() - start

        assert result["status"] == "failed"
        assert "timed out" in result["outcome"].lower()
        # Must complete well within 2× the timeout — not block for another full cycle
        assert elapsed < 1.0, f"Executor blocked for {elapsed:.2f}s after timeout (expected < 1.0s)"

    def test_tool_exception_sets_failed(self, mock_loop):
        """Tool raising an exception must set status='failed' with error text."""
        mock_loop._registry.execute.side_effect = ValueError("bad input")
        mock_loop._registry.get_risk_level.return_value = "low"
        mock_loop._registry.get.return_value = MagicMock()

        step = {"step": 1, "action": "blow up", "tool": "bomb_tool", "params": {}, "risk": "low"}
        result = mock_loop._execute_step(step)
        assert result["status"] == "failed"
        assert "bad input" in result["outcome"]


# ---------------------------------------------------------------------------
# _execute_step edge cases
# ---------------------------------------------------------------------------


class TestExecuteStepEdgeCases:
    def test_null_tool_executes_immediately(self, mock_loop):
        """Steps with tool=None are pure reasoning — executed without registry call."""
        mock_loop._registry.get_risk_level.return_value = "low"
        step = {"step": 1, "action": "think", "tool": None, "params": {}, "risk": "low"}
        result = mock_loop._execute_step(step)
        assert result["status"] == "executed"
        mock_loop._registry.execute.assert_not_called()

    def test_unknown_tool_skipped(self, mock_loop):
        """Tool not in registry must be skipped, not executed."""
        mock_loop._registry.get.return_value = None  # not found
        mock_loop._registry.get_risk_level.return_value = "low"
        step = {"step": 1, "action": "phantom", "tool": "ghost_tool", "params": {}, "risk": "low"}
        result = mock_loop._execute_step(step)
        assert result["status"] == "skipped"
        mock_loop._registry.execute.assert_not_called()

    def test_high_risk_step_blocked(self, mock_loop):
        """High-risk steps must be blocked without calling the registry."""
        mock_loop._registry.get_risk_level.return_value = "high"
        step = {"step": 1, "action": "rm -rf /", "tool": "delete_tool", "params": {}, "risk": "high"}
        result = mock_loop._execute_step(step)
        assert result["status"] == "blocked"
        assert result["blocked"] is True
        mock_loop._registry.execute.assert_not_called()
