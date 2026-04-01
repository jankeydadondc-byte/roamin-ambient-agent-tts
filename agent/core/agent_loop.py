"""Agent loop — plan and execute multi-step tasks using memory, model router, and tools."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import threading

from agent.core.context_builder import ContextBuilder
from agent.core.memory import MemoryManager
from agent.core.model_router import ModelRouter
from agent.core.screen_observer import ScreenObserver
from agent.core.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# Per-step tool execution timeout (seconds). Prevents a single stuck tool from hanging forever.
_TOOL_TIMEOUT_SECONDS = 30


class AgentLoop:
    """
    Reasoning loop: goal -> context -> plan -> execute -> remember.

    Does NOT call input() or block on HITL — high-risk actions are
    flagged in the result and must be approved externally.
    """

    def __init__(self) -> None:
        self._memory = MemoryManager()
        self._router = ModelRouter()
        self._context_builder = ContextBuilder()
        self._registry = ToolRegistry()
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Signal the running run() to stop after the current step completes."""
        self._cancel_event.set()
        logger.info("AgentLoop cancel requested")

    def run(self, goal: str, include_screen: bool = False) -> dict:
        """
        Execute a goal.

        Args:
            goal: Natural language goal
            include_screen: Whether to capture screen before planning

        Returns:
            dict with keys: goal, status, steps, blocked_steps, stored
        """
        result: dict = {
            "goal": goal,
            "status": "started",
            "steps": [],
            "blocked_steps": [],
            "stored": False,
        }

        self._cancel_event.clear()

        # Determine task type and select model
        task_type = self._classify_task(goal)

        # Gather screen context if requested
        screen_obs = None
        if include_screen:
            try:
                screen_obs = ScreenObserver().observe()
            except Exception:
                screen_obs = {"error": "screen observation failed"}

        # Build context
        context = self._context_builder.build(goal, screen_observation=screen_obs)

        # Generate plan from model
        plan = self._generate_plan(goal, context, task_type)
        if plan is None:
            result["status"] = "failed"
            result["error"] = "Could not generate plan (model unreachable or returned invalid response)"
            return result

        # Execute each step — check for cancellation between steps
        for step in plan:
            if self._cancel_event.is_set():
                result["status"] = "cancelled"
                result["cancelled_at_step"] = step.get("step")
                logger.info("AgentLoop cancelled at step %s", step.get("step"))
                return result
            step_result = self._execute_step(step)
            if step_result.get("blocked"):
                result["blocked_steps"].append(step_result)
            else:
                result["steps"].append(step_result)

        # Store in memory
        try:
            self._memory.write_to_memory(
                "action",
                {
                    "action_description": f"AgentLoop goal: {goal}",
                    "outcome": json.dumps({"steps": len(result["steps"]), "blocked": len(result["blocked_steps"])}),
                    "approval_status": "auto",
                },
            )
            result["stored"] = True
        except Exception:
            pass

        result["status"] = "completed" if result["steps"] else "blocked"
        return result

    def _classify_task(self, goal: str) -> str:
        """Simple keyword-based task classification. Returns a model router task key."""
        goal_lower = goal.lower()
        if any(w in goal_lower for w in ["screen", "look at", "see", "observe", "what am i"]):
            return "vision"
        if any(w in goal_lower for w in ["code", "program", "script", "function", "debug", "fix"]):
            return "code"
        if any(w in goal_lower for w in ["reason", "analyze", "analyse"]):
            return "reasoning"
        return "default"

    def _generate_plan(self, goal: str, context: str, task_type: str) -> list[dict] | None:
        """Call the model and parse a list of steps from its response."""
        system_prompt = (
            "You are a task planning assistant. Given a goal and context, "
            "respond with a JSON array of steps. Each step: "
            '{"step": int, "action": str, "tool": str|null, "params": dict, "risk": "low"|"medium"|"high"}. '
            "Use only tools listed in Available Tools. Keep steps minimal and concrete."
        )
        user_prompt = f"{context}\n\nRespond with ONLY a JSON array of steps for this goal."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            content = self._router.respond(task_type, user_prompt, messages=messages, max_tokens=1000, temperature=0.2)

            # Extract JSON from response
            start = content.find("[")
            end = content.rfind("]") + 1
            if start == -1 or end == 0:
                return None
            return json.loads(content[start:end])
        except Exception:
            return None

    def _execute_step(self, step: dict) -> dict:
        """
        Execute a single plan step.

        High-risk steps are NOT executed — they are flagged as blocked
        and must be approved externally (via HITL queue).
        """
        tool_name = step.get("tool")
        risk = step.get("risk", "medium")

        step_result = {
            "step": step.get("step"),
            "action": step.get("action"),
            "tool": tool_name,
            "risk": risk,
            "status": "pending",
            "blocked": False,
        }

        # Block high-risk steps — do not execute
        if risk == "high":
            step_result["status"] = "blocked"
            step_result["blocked"] = True
            step_result["reason"] = "High-risk action requires external approval (HITL)"
            return step_result

        # Auto-approve low and medium risk if tool is in registry
        tool = self._registry.get(tool_name) if tool_name else None
        if tool_name and tool is None:
            step_result["status"] = "skipped"
            step_result["reason"] = f"Tool '{tool_name}' not in registry"
            return step_result

        # Execute low/medium risk tools with a timeout guard
        params = step.get("params") or step.get("parameters") or {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._registry.execute, str(tool_name), params)
            try:
                outcome = future.result(timeout=_TOOL_TIMEOUT_SECONDS)
                step_result["status"] = "executed"
                step_result["outcome"] = str(outcome.get("result") or outcome.get("error", ""))[:1500]
            except concurrent.futures.TimeoutError:
                step_result["status"] = "failed"
                step_result["outcome"] = f"Tool '{tool_name}' timed out after {_TOOL_TIMEOUT_SECONDS}s"
                logger.warning("Tool '%s' timed out after %ds", tool_name, _TOOL_TIMEOUT_SECONDS)
            except Exception as e:
                step_result["status"] = "failed"
                step_result["outcome"] = str(e)[:500]
                logger.warning("Tool '%s' raised exception: %s", tool_name, e)
        return step_result
