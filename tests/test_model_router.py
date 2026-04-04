"""tests/test_model_router.py — Tests for A2 model router."""

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
        assert len(router.list_models()) == 12

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
