"""
model_router.py — Routes tasks to the appropriate local model.
"""

import json
import logging
import time
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "model_config.json"
logger = logging.getLogger(__name__)


class ModelRouter:
    def __init__(self, config_path: Path | None = None):
        self._config_path = config_path or _CONFIG_PATH
        self._config = json.loads(self._config_path.read_text(encoding="utf-8"))
        self._models = {m["id"]: m for m in self._config["models"]}
        self._rules = self._config["routing_rules"]
        self._fallback = self._config["fallback_chain"]

    def select(self, task: str) -> dict:
        """Return the model config dict for a given task type."""
        model_id = self._rules.get(task) or self._rules.get("default")
        model = self._models.get(model_id)
        if model is None:
            for fallback_id in self._fallback:
                if fallback_id in self._models:
                    return self._models[fallback_id]
        return model

    def endpoint(self, task: str) -> str:
        """Return the API base URL for a given task type."""
        return self.select(task)["endpoint"]

    def model_id(self, task: str) -> str:
        """Return the model_id string for a given task type."""
        return self.select(task)["model_id"]

    def has_capability(self, task: str, capability: str) -> bool:
        """Check if the model selected for a task has a specific capability."""
        model = self.select(task)
        return capability in model.get("capabilities", [])

    def best_task_for(self, capability: str) -> str:
        """Return the task key whose model best satisfies the given capability.

        Scans routing rules in declaration order and returns the first task whose
        assigned model declares the given capability. Falls back to 'default' if
        no match is found.

        Use this instead of hardcoding model names — lets model_config.json drive
        routing decisions so adding a new model requires only a config update.

        Args:
            capability: Capability string to search for (e.g., "planning", "deep_thinking").

        Returns:
            Task key string usable with respond(), e.g., "default", "reasoning".
        """
        for task, model_id in self._rules.items():
            model = self._models.get(model_id)
            if model and capability in model.get("capabilities", []):
                return task
        return "default"

    def list_models(self) -> list[dict]:
        """Return all configured models."""
        return list(self._models.values())

    def available_tasks(self) -> list[str]:
        """Return all routable task types."""
        return list(self._rules.keys())

    def respond(
        self,
        task: str,
        prompt: str,
        messages: list[dict] | None = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        no_think: bool = False,
        stream_think: bool = False,
    ) -> str:
        """Generate a response for the given task using LlamaCppBackend (primary) or HTTP fallback.

        Args:
            task: Task type to route (e.g., "code", "vision", "reasoning").
            prompt: Input prompt string.
            messages: Optional list of message dicts for chat mode.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = random).
            no_think: If True, suppress <think> blocks.
            stream_think: If True and no_think is False, print <think> tokens to terminal.

        Returns:
            Model response string.

        Raises:
            RuntimeError: If all inference backends fail.
        """
        # Try LlamaCppBackend first
        try:
            from agent.core.llama_backend import CAPABILITY_MAP, get_llm_response

            if task in CAPABILITY_MAP and CAPABILITY_MAP.get(task) is not None:
                logger.debug("Using LlamaCppBackend for task '%s'", task)
                return get_llm_response(
                    prompt=prompt,
                    capability=task,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
                    no_think=no_think,
                    stream_think=stream_think,
                )
            else:
                logger.debug(
                    "Task '%s' not in CAPABILITY_MAP or GGUF missing, falling back to HTTP",
                    task,
                )
        except ImportError as e:
            logger.debug("llama-cpp-python import failed: %s. Falling back to HTTP", e)

        # Try config-based file_path dispatch (filesystem-discovered models)
        selected = self.select(task)
        if selected and selected.get("file_path"):
            try:
                from agent.core.llama_backend import LlamaCppBackend

                mmproj = Path(selected["mmproj_path"]) if selected.get("mmproj_path") else None
                n_ctx = selected.get("context_window", 8192)
                backend = LlamaCppBackend(
                    model_path=Path(selected["file_path"]),
                    mmproj_path=mmproj,
                    n_ctx=n_ctx,
                )
                backend.load()
                try:
                    if messages is not None:
                        return backend.chat(
                            messages,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            no_think=no_think,
                            stream_think=stream_think,
                        )
                    else:
                        return backend.generate(
                            prompt,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                finally:
                    backend.unload()
            except Exception as e:
                logger.warning(
                    "Config file_path inference failed for task '%s': %s — falling back to HTTP",
                    task,
                    e,
                )

        # Fallback to HTTP (Ollama/LM Studio) with exponential backoff retry
        try:
            import requests

            endpoint = self.endpoint(task).rstrip("/")

            if messages is not None:
                # Chat completion API (LM Studio style)
                url = f"{endpoint}/v1/chat/completions"
                payload = {
                    "model": self.model_id(task),
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                }
            else:
                # Raw generation API (Ollama style)
                url = f"{endpoint}/api/generate"
                payload = {
                    "model": self.model_id(task),
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                }

            max_retries = 2
            last_error: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    response = requests.post(url, json=payload, timeout=5)
                    response.raise_for_status()
                    # Guard against runaway responses from HTTP endpoints (256KB max)
                    if len(response.content) > 256 * 1024:
                        raise RuntimeError(f"Response too large ({len(response.content)} bytes, max 262144)")
                    data = response.json()
                    if messages is not None:
                        return data["choices"][0]["message"]["content"].strip()
                    else:
                        return data.get("response", "").strip()
                except (requests.Timeout, requests.ConnectionError) as e:
                    last_error = e
                    if attempt < max_retries:
                        wait = 2**attempt  # 1s, 2s
                        logger.warning(
                            "HTTP fallback attempt %d/%d failed (%s) — retrying in %ds",
                            attempt + 1,
                            max_retries + 1,
                            e,
                            wait,
                        )
                        time.sleep(wait)
                except KeyError as e:
                    raise RuntimeError(f"Unexpected response format from HTTP endpoint: {e}")

            raise RuntimeError(f"HTTP fallback failed for task '{task}' after {max_retries + 1} attempts: {last_error}")

        except requests.RequestException as e:
            raise RuntimeError(f"HTTP fallback failed for task '{task}' at {self.endpoint(task)}: {e}")
