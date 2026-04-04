"""Tests for 4.2: Dynamic Step Prioritization in AgentLoop."""

from __future__ import annotations

from agent.core.agent_loop import AgentLoop


def _step(tool: str | None, action: str = "", step_num: int = 1) -> dict:
    return {"step": step_num, "tool": tool, "action": action, "params": {}, "risk": "low"}


class TestPriorityScore:
    """Unit tests for AgentLoop._priority_score()."""

    def test_notify_is_high(self):
        assert AgentLoop._priority_score(_step("notify")) == 0

    def test_take_screenshot_is_high(self):
        assert AgentLoop._priority_score(_step("take_screenshot")) == 0

    def test_open_url_is_high(self):
        assert AgentLoop._priority_score(_step("open_url")) == 0

    def test_clipboard_write_is_high(self):
        assert AgentLoop._priority_score(_step("clipboard_write")) == 0

    def test_memory_write_is_low(self):
        assert AgentLoop._priority_score(_step("memory_write")) == 2

    def test_write_file_is_low(self):
        assert AgentLoop._priority_score(_step("write_file")) == 2

    def test_move_file_is_low(self):
        assert AgentLoop._priority_score(_step("move_file")) == 2

    def test_delete_file_is_low(self):
        assert AgentLoop._priority_score(_step("delete_file")) == 2

    def test_web_search_is_medium(self):
        assert AgentLoop._priority_score(_step("web_search")) == 1

    def test_memory_search_is_medium(self):
        assert AgentLoop._priority_score(_step("memory_search")) == 1

    def test_read_file_is_medium(self):
        assert AgentLoop._priority_score(_step("read_file")) == 1

    def test_unknown_tool_is_medium(self):
        assert AgentLoop._priority_score(_step("my_custom_tool")) == 1

    def test_null_tool_is_medium_by_default(self):
        assert AgentLoop._priority_score(_step(None)) == 1

    def test_null_tool_show_action_is_high(self):
        assert AgentLoop._priority_score(_step(None, action="show the user the result")) == 0

    def test_null_tool_notify_action_is_high(self):
        assert AgentLoop._priority_score(_step(None, action="notify the user")) == 0

    def test_null_tool_store_action_is_low(self):
        assert AgentLoop._priority_score(_step(None, action="store result in database")) == 2

    def test_null_tool_save_action_is_low(self):
        assert AgentLoop._priority_score(_step(None, action="save the output to file")) == 2


class TestPlanSorting:
    """Integration: plan is sorted before execution."""

    def test_notify_bubbles_above_memory_write(self):
        plan = [
            _step("memory_write", step_num=1),
            _step("notify", step_num=2),
        ]
        sorted_plan = sorted(plan, key=AgentLoop._priority_score)
        assert sorted_plan[0]["tool"] == "notify"
        assert sorted_plan[1]["tool"] == "memory_write"

    def test_full_priority_order(self):
        plan = [
            _step("memory_write", step_num=1),  # LOW
            _step("web_search", step_num=2),  # MED
            _step("notify", step_num=3),  # HIGH
        ]
        sorted_plan = sorted(plan, key=AgentLoop._priority_score)
        tools = [s["tool"] for s in sorted_plan]
        assert tools == ["notify", "web_search", "memory_write"]

    def test_equal_priority_stable_order(self):
        """Equal-priority steps must retain their original order (stable sort)."""
        plan = [
            _step("web_search", step_num=1),
            _step("memory_search", step_num=2),
            _step("clipboard_read", step_num=3),
        ]
        sorted_plan = sorted(plan, key=AgentLoop._priority_score)
        step_nums = [s["step"] for s in sorted_plan]
        assert step_nums == [1, 2, 3]

    def test_all_high_retain_original_order(self):
        plan = [
            _step("notify", step_num=1),
            _step("open_url", step_num=2),
            _step("take_screenshot", step_num=3),
        ]
        sorted_plan = sorted(plan, key=AgentLoop._priority_score)
        step_nums = [s["step"] for s in sorted_plan]
        assert step_nums == [1, 2, 3]

    def test_single_step_unaffected(self):
        plan = [_step("web_search", step_num=1)]
        sorted_plan = sorted(plan, key=AgentLoop._priority_score)
        assert sorted_plan == plan

    def test_empty_plan_unaffected(self):
        assert sorted([], key=AgentLoop._priority_score) == []
