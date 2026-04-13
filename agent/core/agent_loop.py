"""Agent loop — plan and execute multi-step tasks using memory, model router, and tools."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable

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

    # Expose tool registry for plugin loading at startup (read-only access)
    @property
    def registry(self) -> ToolRegistry:
        """Return the tool registry so plugins can register tools at startup."""
        return self._registry

    def cancel(self) -> None:
        """Signal the running run() to stop after the current step completes."""
        self._cancel_event.set()
        logger.info("AgentLoop cancel requested")

    def run(
        self,
        goal: str,
        include_screen: bool = False,
        on_progress: Callable[[dict], None] | None = None,
        session_context: str | None = None,
    ) -> dict:
        """
        Execute a goal.

        Args:
            goal: Natural language goal
            include_screen: Whether to capture screen before planning
            session_context: Optional session transcript for conversation continuity

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

        # Pre-flight: verify required dependencies are present before proceeding
        ready, readiness_msg = self._check_feature_ready(task_type)
        if not ready:
            result["status"] = "failed"
            result["error"] = readiness_msg
            return result

        # Start task history record (non-fatal if it fails)
        task_run_id: int | None = None
        try:
            task_run_id = self._memory.start_task(goal, task_type)
        except Exception:
            pass

        # Gather screen context if requested
        screen_obs = None
        if include_screen:
            try:
                screen_obs = ScreenObserver().observe()
            except Exception:
                screen_obs = {"error": "screen observation failed"}

        # Build context — pass self._registry so plugin tools appear in the tool list
        context = self._context_builder.build(  # type: ignore[call-arg]
            goal, screen_observation=screen_obs, registry=self._registry, session_context=session_context
        )

        # Generate plan from model
        if on_progress:
            on_progress({"phase": "planning", "detail": "Planning..."})
        plan = self._generate_plan(goal, context, task_type)
        if plan is None:
            result["status"] = "failed"
            result["error"] = "Could not generate plan (model unreachable or returned invalid response)"
            if task_run_id is not None:
                try:
                    self._memory.finish_task(task_run_id, "failed", 0)
                except Exception:
                    pass
            return result

        # Sort steps by priority before execution: HIGH first, LOW last (stable sort)
        plan = sorted(plan, key=self._priority_score)

        if on_progress:
            on_progress({"phase": "executing", "total_steps": len(plan)})

        # Execute each step — check for cancellation between steps
        for i, step in enumerate(plan):
            if self._cancel_event.is_set():
                result["status"] = "cancelled"
                result["cancelled_at_step"] = step.get("step")
                logger.info("AgentLoop cancelled at step %s", step.get("step"))
                if task_run_id is not None:
                    try:
                        self._memory.finish_task(task_run_id, "cancelled", len(result["steps"]))
                    except Exception:
                        pass
                return result
            if on_progress:
                on_progress(
                    {
                        "phase": "step_start",
                        "step": i + 1,
                        "total_steps": len(plan),
                        "detail": (step.get("action") or "")[:60],
                    }
                )
            step_start_time = time.perf_counter()
            step_result = self._execute_step(step)
            step_duration_ms = int((time.perf_counter() - step_start_time) * 1000)
            if on_progress:
                on_progress(
                    {
                        "phase": "step_done",
                        "step": i + 1,
                        "total_steps": len(plan),
                        "status": step_result.get("status"),
                    }
                )
            # Log step to task history (non-fatal)
            if task_run_id is not None:
                try:
                    self._memory.log_step(
                        task_run_id,
                        i + 1,
                        step.get("tool"),
                        step.get("action"),
                        json.dumps(step.get("params", {})),
                        (step_result.get("outcome") or "")[:1500],
                        step_result.get("status", "unknown"),
                        step_duration_ms,
                    )
                except Exception:
                    pass
            if step_result.get("blocked"):
                result["blocked_steps"].append(step_result)
            else:
                result["steps"].append(step_result)

        # Store in memory (legacy actions_taken table — kept for backward compat)
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

        # Derive status from step outcomes — not just presence of steps (#7)
        if not result["steps"]:
            result["status"] = "blocked"
        elif all(s.get("status") == "failed" for s in result["steps"]):
            result["status"] = "failed"
        elif any(s.get("status") == "failed" for s in result["steps"]):
            result["status"] = "partial"
        else:
            result["status"] = "completed"

        # Finish task history record
        if task_run_id is not None:
            try:
                self._memory.finish_task(task_run_id, result["status"], len(result["steps"]))
            except Exception:
                pass

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

    @staticmethod
    def _check_feature_ready(capability: str) -> tuple[bool, str]:
        """Pre-flight check for a named capability.

        Returns:
            (ready: bool, message: str)
            If ready=False, message is a TTS-safe English sentence explaining the failure.
        """
        if capability == "vision":
            try:
                import importlib

                importlib.import_module("PIL")
            except ImportError:
                return False, "Vision is unavailable: Pillow is not installed."
            try:
                from agent.core.llama_backend import QWEN3_VL_8B_MMPROJ

                if QWEN3_VL_8B_MMPROJ is None:
                    return False, "Vision is unavailable: the multimodal projection file is missing."
            except ImportError:
                return False, "Vision is unavailable: llama-cpp-python backend not found."
        return True, ""

    @staticmethod
    def _priority_score(step: dict) -> int:
        """Priority sort key for a plan step. Lower score = execute first.

        HIGH (0): user-visible output actions (notify, screenshot, open URL, clipboard write)
        MED  (1): data retrieval and reads (web search, memory search, file reads) — default
        LOW  (2): background writes and storage (memory write, file write, move, delete)
        """
        tool = (step.get("tool") or "").lower()
        action = (step.get("action") or "").lower()
        _HIGH_TOOLS = frozenset({"notify", "take_screenshot", "open_url", "clipboard_write"})
        _LOW_TOOLS = frozenset({"memory_write", "write_file", "move_file", "delete_file"})
        if tool in _HIGH_TOOLS:
            return 0
        if tool in _LOW_TOOLS:
            return 2
        if any(w in action for w in ("notif", "alert", "show", "display", "open")):
            return 0
        if any(w in action for w in ("store", "save", "log", "record", "write")):
            return 2
        return 1

    def _should_throttle(self) -> bool:
        """Return True if system resources are exhausted and the step should be deferred."""
        try:
            from agent.core.resource_monitor import is_resource_exhausted

            return is_resource_exhausted()
        except Exception:
            return False  # Fail open — never block execution on monitoring failure

    def _cleanup_completed_tasks(self, older_than_hours: int = 24) -> dict:
        """Delete completed/failed/partial task_runs older than cutoff (#8).

        Returns dict with ``deleted_count`` and ``oldest_retained_ts``.
        """
        from datetime import datetime, timedelta
        from pathlib import Path

        db_path = Path(str(self._memory.store.db_path))
        if not db_path.exists():
            return {"deleted_count": 0, "oldest_retained_ts": None}

        cutoff = (datetime.now() - timedelta(hours=older_than_hours)).isoformat()
        try:
            with sqlite3.connect(str(db_path)) as conn:
                cur = conn.execute(
                    "DELETE FROM task_runs WHERE status IN ('completed', 'failed', 'partial')" " AND started_at < ?",
                    (cutoff,),
                )
                deleted = cur.rowcount
            logger.info("Task cleanup: deleted %d rows older than %dh", deleted, older_than_hours)
            return {"deleted_count": deleted, "oldest_retained_ts": None}
        except Exception as exc:
            logger.warning("Task cleanup failed: %s", exc)
            return {"deleted_count": 0, "oldest_retained_ts": None}

    def _generate_plan(self, goal: str, context: str, task_type: str) -> list[dict] | None:
        """Call the model and parse a list of steps from its response."""
        system_prompt = (
            "You are a task planning assistant. Output ONLY a JSON array of steps. "
            'Each step: {"step": int, "action": str, "tool": str|null, "params": dict, "risk": "low"|"medium"|"high"}. '
            "RULE: If a suitable tool exists in Available Tools, you MUST use it (set tool=<name>). "
            "Only use tool=null for pure reasoning steps where no tool applies. "
            "Use only tools listed in Available Tools. Keep steps minimal and concrete."
        )
        user_prompt = f"{context}\n\nRespond with ONLY a JSON array of steps for this goal."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            # Use capability-based routing: find whichever model is declared capable
            # of structured planning (JSON output). This avoids hardcoding "default"
            # and allows model_config.json to drive the decision — if a better planning
            # model is added later, just add "planning" to its capabilities.
            planning_task = self._router.best_task_for("planning")
            content = self._router.respond(
                planning_task, user_prompt, messages=messages, max_tokens=1000, temperature=0.2
            )

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

        # Throttle check — skip when ROAMIN_USE_ASYNC is off (default)
        if os.environ.get("ROAMIN_USE_ASYNC", "").lower() == "1" and self._should_throttle():
            step_result["status"] = "skipped"
            step_result["reason"] = "System resources exhausted — throttled"
            return step_result

        # Block high-risk steps — do not execute
        if risk == "high":
            step_result["status"] = "blocked"
            step_result["blocked"] = True
            step_result["reason"] = "High-risk action requires external approval (HITL)"
            return step_result

        # Null-tool step — pure reasoning or descriptive action, nothing to execute
        if not tool_name:
            step_result["status"] = "executed"
            step_result["outcome"] = ""
            return step_result

        # Auto-approve low and medium risk if tool is in registry
        tool = self._registry.get(tool_name) if tool_name else None
        if tool_name and tool is None:
            step_result["status"] = "skipped"
            step_result["reason"] = f"Tool '{tool_name}' not in registry"
            return step_result

        # Execute low/medium risk tools with a non-blocking timeout guard (#6)
        # Avoid context-manager so __exit__ doesn't block on a still-running timed-out thread.
        params = step.get("params") or step.get("parameters") or {}
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._registry.execute, str(tool_name), params)
        try:
            outcome = future.result(timeout=_TOOL_TIMEOUT_SECONDS)
            step_result["status"] = "executed"
            step_result["outcome"] = str(outcome.get("result") or outcome.get("error", ""))[:1500]
        except concurrent.futures.TimeoutError:
            future.cancel()
            step_result["status"] = "failed"
            step_result["outcome"] = f"Tool '{tool_name}' timed out after {_TOOL_TIMEOUT_SECONDS}s"
            logger.warning("Tool '%s' timed out after %ds", tool_name, _TOOL_TIMEOUT_SECONDS)
        except Exception as e:
            step_result["status"] = "failed"
            step_result["outcome"] = str(e)[:500]
            logger.warning("Tool '%s' raised exception: %s", tool_name, e)
        finally:
            # cancel_futures=True abandons still-running thread; don't block caller (#6)
            executor.shutdown(wait=False, cancel_futures=True)
        return step_result
