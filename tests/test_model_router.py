"""tests/test_model_router.py — Tests for A2 model router."""

import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Environment guard: `requests` may not be installed when tests run under the
# system Python rather than the project venv. Pre-stub the module so:
#   (a) patch("requests.post", ...) can resolve its target, and
#   (b) the lazy `import requests` inside model_router.respond() gets the mock.
# Exception classes map to real built-ins so except clauses in model_router.py
# (requests.Timeout, requests.ConnectionError, requests.RequestException) work.
# When running under the project venv (requests IS installed), guard skips
# entirely — tests run against the real library as normal.
# ---------------------------------------------------------------------------
if "requests" not in sys.modules:
    _req_stub = types.ModuleType("requests")
    _req_stub.Timeout = TimeoutError
    _req_stub.ConnectionError = ConnectionError
    _req_stub.RequestException = Exception
    _req_stub.post = MagicMock()  # placeholder so patch("requests.post", ...) can replace it
    sys.modules["requests"] = _req_stub

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
        # v14 cleanup left 27 models in config; allow for dynamic discovery variance (#102)
        models = router.list_models()
        assert len(models) >= 20, f"Expected >= 20 models after v14 config cleanup, got {len(models)}"

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
        assert "262145" in error_msg
        assert "max 262144" in error_msg


class TestAuthHeaders:
    """Verify _auth_headers attaches Bearer tokens correctly."""

    def test_no_token_no_auth_header(self, router, monkeypatch):
        """Without LM_API_TOKEN, no Authorization header is sent."""
        monkeypatch.delenv("LM_API_TOKEN", raising=False)
        headers = router._auth_headers("default")
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_global_lm_api_token(self, router, monkeypatch):
        """LM_API_TOKEN env var attaches as Bearer token."""
        monkeypatch.setenv("LM_API_TOKEN", "sk-lm-test-123")
        headers = router._auth_headers("default")
        assert headers["Authorization"] == "Bearer sk-lm-test-123"

    def test_per_model_api_key_env(self, router, monkeypatch):
        """Per-model api_key_env overrides global LM_API_TOKEN."""
        monkeypatch.setenv("LM_API_TOKEN", "sk-global-fallback")
        monkeypatch.setenv("CUSTOM_KEY", "sk-custom-per-model")
        # Patch a model to have api_key_env pointing to CUSTOM_KEY
        with patch.object(
            router,
            "select",
            return_value={"api_key_env": "CUSTOM_KEY", "endpoint": "http://127.0.0.1:1234"},
        ):
            headers = router._auth_headers("default")
        assert headers["Authorization"] == "Bearer sk-custom-per-model"

    def test_per_model_env_var_missing_falls_back_to_global(self, router, monkeypatch):
        """If per-model env var is not set, falls back to LM_API_TOKEN."""
        monkeypatch.setenv("LM_API_TOKEN", "sk-global-fallback")
        monkeypatch.delenv("MISSING_KEY", raising=False)
        with patch.object(
            router,
            "select",
            return_value={"api_key_env": "MISSING_KEY", "endpoint": "http://127.0.0.1:1234"},
        ):
            headers = router._auth_headers("default")
        assert headers["Authorization"] == "Bearer sk-global-fallback"
