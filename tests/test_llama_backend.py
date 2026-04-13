"""tests/test_llama_backend.py — unit tests for LlamaCppBackend / ModelRegistry.

Fast unit tests require no GPU or GGUF files.
Tests that need actual hardware are marked @pytest.mark.integration (#108).
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Fast unit tests — no GPU required
# ---------------------------------------------------------------------------


class TestCapabilityMap:
    def test_capability_map_is_dict(self):
        """CAPABILITY_MAP must be a non-empty dict."""
        from agent.core.llama_backend import CAPABILITY_MAP

        assert isinstance(CAPABILITY_MAP, dict)
        assert len(CAPABILITY_MAP) > 0

    def test_capability_map_keys_are_strings(self):
        """All CAPABILITY_MAP keys must be strings."""
        from agent.core.llama_backend import CAPABILITY_MAP

        for key in CAPABILITY_MAP:
            assert isinstance(key, str), f"Non-string capability key: {key!r}"

    def test_known_capabilities_present(self):
        """Standard capabilities used by ModelRouter must be registered."""
        from agent.core.llama_backend import CAPABILITY_MAP

        expected = {"fast", "code", "reasoning"}
        missing = expected - set(CAPABILITY_MAP.keys())
        assert not missing, f"Missing capabilities: {missing}"


class TestModelRegistryUnit:
    def test_get_backend_raises_on_unknown_capability(self):
        """ModelRegistry.get_backend() must raise RuntimeError for unknown capability (#108)."""
        from agent.core.llama_backend import ModelRegistry

        registry = ModelRegistry()
        with pytest.raises(RuntimeError, match="No GGUF model registered"):
            registry.get_backend("nonexistent_capability_xyzzy")

    def test_get_backend_raises_when_model_path_none(self):
        """Capability mapped to None (disabled model) must raise RuntimeError."""
        from unittest.mock import patch

        from agent.core.llama_backend import ModelRegistry

        registry = ModelRegistry()
        # Temporarily add a None-mapped capability
        with patch("agent.core.llama_backend.CAPABILITY_MAP", {"test_disabled": None}):
            with pytest.raises(RuntimeError):
                registry.get_backend("test_disabled")


# ---------------------------------------------------------------------------
# Integration tests — require GPU + GGUF files on disk
# Run with: pytest -m integration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLlamaBackendIntegration:
    """These tests need actual GGUF model files and GPU hardware."""

    def test_fast_capability_loads_and_generates(self):
        pytest.skip("Requires GGUF model on disk and GPU — run manually with: pytest -m integration")

    def test_model_unloads_on_capability_switch(self):
        pytest.skip("Requires two loaded GGUF models — run manually with: pytest -m integration")
