"""Vision model integration tests.

Validates the dynamic capability map for vision routing:
1. CAPABILITY_MAP contains expected capabilities (model-agnostic)
2. Vision capabilities have a paired mmproj in _MMPROJ_MAP
3. ModelRegistry loads vision capability with mmproj attached
4. Basic chat inference produces a response (requires GPU)
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.core.llama_backend import _MMPROJ_MAP, _VISION_CAPABILITIES, CAPABILITY_MAP  # noqa: E402


def test_capability_map_routes():
    """Verify core capabilities are registered and resolve to real files."""
    print("Test 1: CAPABILITY_MAP routing...")
    for cap in ("default", "chat", "fast"):
        model_path = CAPABILITY_MAP.get(cap)
        assert model_path is not None, f"'{cap}' not in CAPABILITY_MAP — no matching model found on disk"
        assert model_path.exists(), f"'{cap}' model file missing: {model_path}"
        print(f"  {cap}: {model_path.name}")
    print("  PASS: Core capabilities registered and files exist")


def test_vision_capability():
    """Verify vision capability exists and has a paired mmproj."""
    print("\nTest 2: Vision capability...")
    vision_path = CAPABILITY_MAP.get("vision")
    if vision_path is None:
        print("  SKIP: No vision model found on disk (no VL model with mmproj)")
        return

    assert vision_path.exists(), f"Vision model file missing: {vision_path}"
    print(f"  Model: {vision_path.name}")

    mmproj = _MMPROJ_MAP.get(vision_path)
    assert mmproj is not None, f"Vision model has no paired mmproj in _MMPROJ_MAP: {vision_path.name}"
    assert mmproj.exists(), f"mmproj file missing: {mmproj}"
    print(f"  mmproj: {mmproj.name}")

    assert "vision" in _VISION_CAPABILITIES, "'vision' not in _VISION_CAPABILITIES"
    assert "screen_reading" in _VISION_CAPABILITIES, "'screen_reading' not in _VISION_CAPABILITIES"
    print("  PASS: Vision capability has mmproj and is in _VISION_CAPABILITIES")


def test_mmproj_map_consistency():
    """Verify every vision capability's model has a paired mmproj."""
    print("\nTest 3: _MMPROJ_MAP consistency...")
    for cap in _VISION_CAPABILITIES:
        model_path = CAPABILITY_MAP.get(cap)
        if model_path is None:
            continue  # Capability not registered (model absent) — fine
        mmproj = _MMPROJ_MAP.get(model_path)
        assert mmproj is not None, (
            f"Vision capability '{cap}' is in _VISION_CAPABILITIES but its model "
            f"({model_path.name}) has no entry in _MMPROJ_MAP"
        )
        assert mmproj.exists(), f"mmproj missing for '{cap}': {mmproj}"
    print(f"  PASS: All {len(_VISION_CAPABILITIES)} vision capabilities have paired mmproj")


def test_model_registry_loads():
    """Verify ModelRegistry correctly loads default (text-only) and vision (with mmproj)."""
    print("\nTest 4: ModelRegistry.get_backend...")
    try:
        from agent.core.llama_backend import ModelRegistry

        registry = ModelRegistry()

        # default capability: text-only, mmproj should NOT be loaded
        print("  Loading 'default' (text-only)...")
        backend = registry.get_backend("default")
        assert backend.is_loaded(), "Backend not loaded after get_backend('default')"
        assert backend.mmproj_path is None, "default capability should not load mmproj"
        print(f"  PASS: {backend.model_path.name} loaded without mmproj")
        registry.unload_all()

        # vision capability: mmproj MUST be loaded (skip if not available)
        if "vision" in CAPABILITY_MAP:
            print("  Loading 'vision' (with mmproj)...")
            vision_backend = registry.get_backend("vision")
            assert vision_backend.is_loaded(), "Backend not loaded after get_backend('vision')"
            assert vision_backend.mmproj_path is not None, "vision capability must load mmproj"
            print(f"  PASS: {vision_backend.model_path.name} loaded with mmproj {vision_backend.mmproj_path.name}")
            registry.unload_all()
        else:
            print("  SKIP: 'vision' capability not registered (no VL model on disk)")

        print("  Model unloaded successfully")
    except RuntimeError as e:
        if "llama-cpp-python" in str(e):
            print(f"  SKIP: llama-cpp-python not installed ({e})")
        else:
            print(f"  FAIL: {e}")
            raise


def test_basic_chat():
    """Verify basic chat inference works (requires GPU + llama-cpp-python)."""
    print("\nTest 5: Basic chat inference...")
    try:
        from agent.core.llama_backend import get_llm_response

        response = get_llm_response(
            prompt="",
            capability="default",
            messages=[{"role": "user", "content": "What is 2+2? Reply with just the number."}],
            max_tokens=20,
            temperature=0.1,
            no_think=True,
        )
        print(f"  Response: {response[:100]}")
        assert len(response) > 0, "Empty response from model"
        print("  PASS: Model produced a response")
    except RuntimeError as e:
        if "llama-cpp-python" in str(e):
            print(f"  SKIP: llama-cpp-python not installed ({e})")
        else:
            print(f"  FAIL: {e}")
            raise


if __name__ == "__main__":
    print("=" * 60)
    print("Dynamic Capability Map — Vision Integration Tests")
    print("=" * 60)

    test_capability_map_routes()
    test_vision_capability()
    test_mmproj_map_consistency()
    test_model_registry_loads()
    test_basic_chat()

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)
