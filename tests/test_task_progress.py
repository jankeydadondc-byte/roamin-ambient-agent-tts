"""Tests for 6.1 — Task Progress Callbacks."""

from unittest.mock import MagicMock, patch

from agent.core.agent_loop import AgentLoop


class TestProgressCallbackSequence:
    """Verify on_progress receives events in the correct order."""

    @patch.object(AgentLoop, "_generate_plan")
    @patch.object(AgentLoop, "_execute_step")
    @patch.object(AgentLoop, "_classify_task", return_value="default")
    @patch.object(AgentLoop, "__init__", return_value=None)
    def test_progress_events_in_order(self, _init, _classify, mock_exec, mock_plan):
        """Events emitted: planning → executing → step_start → step_done for each step."""
        loop = AgentLoop.__new__(AgentLoop)
        loop._cancel_event = MagicMock()
        loop._cancel_event.is_set.return_value = False
        loop._cancel_event.clear = MagicMock()
        loop._memory = MagicMock()
        loop._context_builder = MagicMock()
        loop._context_builder.build.return_value = "ctx"

        mock_plan.return_value = [
            {"step": 1, "action": "Search", "tool": "web_search", "params": {}, "risk": "low"},
            {"step": 2, "action": "Notify", "tool": "notify", "params": {}, "risk": "low"},
            {"step": 3, "action": "Store", "tool": "memory_write", "params": {}, "risk": "low"},
        ]
        mock_exec.return_value = {"status": "executed", "outcome": "ok"}

        events = []
        loop.run("test goal", on_progress=lambda e: events.append(e))

        phases = [e["phase"] for e in events]
        assert phases == [
            "planning",
            "executing",
            "step_start",
            "step_done",
            "step_start",
            "step_done",
            "step_start",
            "step_done",
        ]

    @patch.object(AgentLoop, "_generate_plan")
    @patch.object(AgentLoop, "_execute_step")
    @patch.object(AgentLoop, "_classify_task", return_value="default")
    @patch.object(AgentLoop, "__init__", return_value=None)
    def test_step_numbers_correct(self, _init, _classify, mock_exec, mock_plan):
        """step_start events carry correct step number and total_steps."""
        loop = AgentLoop.__new__(AgentLoop)
        loop._cancel_event = MagicMock()
        loop._cancel_event.is_set.return_value = False
        loop._cancel_event.clear = MagicMock()
        loop._memory = MagicMock()
        loop._context_builder = MagicMock()
        loop._context_builder.build.return_value = "ctx"

        mock_plan.return_value = [
            {"step": 1, "action": "A", "tool": "web_search", "params": {}, "risk": "low"},
            {"step": 2, "action": "B", "tool": "notify", "params": {}, "risk": "low"},
        ]
        mock_exec.return_value = {"status": "executed", "outcome": "ok"}

        events = []
        loop.run("test", on_progress=lambda e: events.append(e))

        step_starts = [e for e in events if e["phase"] == "step_start"]
        assert len(step_starts) == 2
        assert step_starts[0]["step"] == 1
        assert step_starts[0]["total_steps"] == 2
        assert step_starts[1]["step"] == 2


class TestProgressCallbackOptional:
    """Verify on_progress=None preserves existing behavior."""

    @patch.object(AgentLoop, "_generate_plan")
    @patch.object(AgentLoop, "_execute_step")
    @patch.object(AgentLoop, "_classify_task", return_value="default")
    @patch.object(AgentLoop, "__init__", return_value=None)
    def test_no_error_without_callback(self, _init, _classify, mock_exec, mock_plan):
        """run() works identically when on_progress is None."""
        loop = AgentLoop.__new__(AgentLoop)
        loop._cancel_event = MagicMock()
        loop._cancel_event.is_set.return_value = False
        loop._cancel_event.clear = MagicMock()
        loop._memory = MagicMock()
        loop._context_builder = MagicMock()
        loop._context_builder.build.return_value = "ctx"

        mock_plan.return_value = [
            {"step": 1, "action": "Do thing", "tool": "notify", "params": {}, "risk": "low"},
        ]
        mock_exec.return_value = {"status": "executed", "outcome": "ok"}

        result = loop.run("test goal")  # on_progress defaults to None
        assert result["status"] == "completed"
        assert len(result["steps"]) == 1


class TestProgressWithCancellation:
    """Verify no progress events after cancellation."""

    @patch.object(AgentLoop, "_generate_plan")
    @patch.object(AgentLoop, "_execute_step")
    @patch.object(AgentLoop, "_classify_task", return_value="default")
    @patch.object(AgentLoop, "__init__", return_value=None)
    def test_no_progress_after_cancel(self, _init, _classify, mock_exec, mock_plan):
        """After cancel event is set, no further step_start/step_done events."""
        loop = AgentLoop.__new__(AgentLoop)
        loop._cancel_event = MagicMock()
        # Cancel before step 2
        loop._cancel_event.is_set.side_effect = [False, True]
        loop._cancel_event.clear = MagicMock()
        loop._memory = MagicMock()
        loop._context_builder = MagicMock()
        loop._context_builder.build.return_value = "ctx"

        mock_plan.return_value = [
            {"step": 1, "action": "A", "tool": "web_search", "params": {}, "risk": "low"},
            {"step": 2, "action": "B", "tool": "notify", "params": {}, "risk": "low"},
        ]
        mock_exec.return_value = {"status": "executed", "outcome": "ok"}

        events = []
        result = loop.run("test", on_progress=lambda e: events.append(e))

        assert result["status"] == "cancelled"
        step_starts = [e for e in events if e["phase"] == "step_start"]
        # Only step 1 got a step_start — step 2 was cancelled before it started
        assert len(step_starts) == 1
        assert step_starts[0]["step"] == 1


class TestProgressDetailTruncation:
    """Verify action detail is truncated in progress events."""

    @patch.object(AgentLoop, "_generate_plan")
    @patch.object(AgentLoop, "_execute_step")
    @patch.object(AgentLoop, "_classify_task", return_value="default")
    @patch.object(AgentLoop, "__init__", return_value=None)
    def test_action_detail_truncated_to_60_chars(self, _init, _classify, mock_exec, mock_plan):
        """step_start detail is truncated to 60 characters."""
        loop = AgentLoop.__new__(AgentLoop)
        loop._cancel_event = MagicMock()
        loop._cancel_event.is_set.return_value = False
        loop._cancel_event.clear = MagicMock()
        loop._memory = MagicMock()
        loop._context_builder = MagicMock()
        loop._context_builder.build.return_value = "ctx"

        long_action = "A" * 100
        mock_plan.return_value = [
            {"step": 1, "action": long_action, "tool": "notify", "params": {}, "risk": "low"},
        ]
        mock_exec.return_value = {"status": "executed", "outcome": "ok"}

        events = []
        loop.run("test", on_progress=lambda e: events.append(e))

        step_start = [e for e in events if e["phase"] == "step_start"][0]
        assert len(step_start["detail"]) == 60
