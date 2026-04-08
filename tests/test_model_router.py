"""tests/test_model_router.py — Tests for A2 model router."""

import json
from unittest.mock import MagicMock, patch

import pytest

from agent.core.model_router import ModelRouter


@pytest.fixture
def router():
    return ModelRouter()


class TestModelRouter:
    def test_default_task_routes_to_llama_cpp(self, router):
        assert router.endpoint("default") == "local://llama_cpp"
        assert "qwen3-vl" in router.model_id("default").lower() or "abliterated" in router.model_id("default").lower()

    def test_code_task_routes_to_coder(self, router):
        assert "coder" in router.model_id("code")

    def test_vision_task_routes_to_llama_cpp(self, router):
        assert router.endpoint("vision") == "local://llama_cpp"

    def test_vision_has_screen_reading_capability(self, router):
        assert router.has_capability("vision", "screen_reading") is True

    def test_reasoning_routes_to_deepseek(self, router):
        assert "deepseek" in router.model_id("reasoning").lower() or "r1" in router.model_id("reasoning").lower()

    def test_fast_routes_to_small_model(self, router):
        assert "8b" in router.model_id("fast").lower()

    def test_unknown_task_returns_default(self, router):
        result = router.select("nonexistent_task")
        assert result is not None
        assert "model_id" in result

    def test_list_models_returns_all_models(self, router):
        # model_sync auto-discovers additional models at runtime, so check >= base count
        assert len(router.list_models()) >= 12

    def test_all_models_have_required_fields(self, router):
        for m in router.list_models():
            assert "id" in m
            assert "endpoint" in m
            assert "model_id" in m
            assert "capabilities" in m

    def test_available_tasks_not_empty(self, router):
        tasks = router.available_tasks()
        assert len(tasks) > 0
        assert "default" in tasks
        assert "vision" in tasks
        assert "code" in tasks


class TestHttpFallbackSizeLimit:
    """Verify the 256KB response size guard in the HTTP fallback path."""

    # Task name that is intentionally not in CAPABILITY_MAP so llama_cpp is skipped
    _HTTP_TASK = "_test_http_only_task_"

    def _force_http_path(self, router, mock_post):
        """Context stack that routes respond() to the mocked HTTP endpoint.

        Strategy: use a task absent from CAPABILITY_MAP so llama_cpp is skipped,
        mock select() to return a config entry with no file_path so the filesystem
        dispatch is also skipped, then intercept requests.post.
        """
        return (
            patch.object(router, "select", return_value={}),
            patch.object(router, "endpoint", return_value="http://127.0.0.1:1234"),
            patch.object(router, "model_id", return_value="test-model"),
            patch("requests.post", return_value=mock_post),
        )

    def test_normal_chat_response_passes_through(self, router):
        """Chat response under 256KB reaches caller unchanged."""
        # Build a minimal chat-completion JSON body
        payload = {"choices": [{"message": {"content": "hello world"}}]}
        mock_resp = MagicMock()
        mock_resp.content = json.dumps(payload).encode()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = payload

        ctx = self._force_http_path(router, mock_resp)
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            result = router.respond(
                self._HTTP_TASK,
                "hi",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert result == "hello world"

    def test_normal_raw_response_passes_through(self, router):
        """Raw/Ollama response under 256KB reaches caller unchanged."""
        payload = {"response": "ollama says hi"}
        mock_resp = MagicMock()
        mock_resp.content = json.dumps(payload).encode()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = payload

        ctx = self._force_http_path(router, mock_resp)
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            # No messages= kwarg triggers the raw/Ollama code path
            result = router.respond(self._HTTP_TASK, "hi")

        assert result == "ollama says hi"

    def test_oversized_response_raises_runtime_error(self, router):
        """Response exceeding 256KB raises RuntimeError with byte count and limit."""
        oversized = b"x" * (256 * 1024 + 1)  # exactly one byte over the limit
        mock_resp = MagicMock()
        mock_resp.content = oversized
        mock_resp.raise_for_status.return_value = None

        ctx = self._force_http_path(router, mock_resp)
        with ctx[0], ctx[1], ctx[2], ctx[3]:
            with pytest.raises(RuntimeError) as exc_info:
                router.respond(
                    self._HTTP_TASK,
                    "hi",
                    messages=[{"role": "user", "content": "hi"}],
                )

        error_msg = str(exc_info.value)
        # Actual byte count must appear so the log is useful for debugging
        assert "262145" in error_msg
        # The hard limit must also appear so it's clear what the threshold is
        assert "max 262144" in error_msg
