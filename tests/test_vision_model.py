"""Tests for Qwen3-VL-8B abliterated vision model integration.

Validates that:
1. CAPABILITY_MAP routes default/chat/fast/vision to the new model
2. Model and mmproj files exist on disk
3. _MMPROJ_MAP correctly resolves mmproj for vision-capable models
4. ModelRegistry.get_backend() loads the model with mmproj attached
5. Basic chat inference produces a response (requires GPU)
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.core.llama_backend import _MMPROJ_MAP, CAPABILITY_MAP, QWEN3_VL_8B, QWEN3_VL_8B_MMPROJ  # noqa: E402


def test_capability_map_routes():
    """Verify default/chat/fast/vision all point to Qwen3-VL-8B."""
    print("Test 1: CAPABILITY_MAP routing...")
    for cap in ("default", "chat", "fast", "vision", "screen_reading"):
        model_path = CAPABILITY_MAP.get(cap)
        assert model_path is not None, f"'{cap}' not in CAPABILITY_MAP or resolved to None"
        assert "abliterated" in str(model_path).lower(), f"'{cap}' does not point to abliterated model: {model_path}"
    print("  PASS: All 5 capabilities route to Qwen3-VL-8B abliterated")


def test_model_files_exist():
    """Verify GGUF files are on disk."""
    print("\nTest 2: Model files exist...")
    assert QWEN3_VL_8B is not None, "QWEN3_VL_8B is None (file missing)"
    assert QWEN3_VL_8B.exists(), f"Model file not found: {QWEN3_VL_8B}"
    size_gb = QWEN3_VL_8B.stat().st_size / (1024**3)
    print(f"  Model: {QWEN3_VL_8B.name} ({size_gb:.2f} GB)")

    assert QWEN3_VL_8B_MMPROJ is not None, "QWEN3_VL_8B_MMPROJ is None (file missing)"
    assert QWEN3_VL_8B_MMPROJ.exists(), f"mmproj file not found: {QWEN3_VL_8B_MMPROJ}"
    mmproj_mb = QWEN3_VL_8B_MMPROJ.stat().st_size / (1024**2)
    print(f"  mmproj: {QWEN3_VL_8B_MMPROJ.name} ({mmproj_mb:.0f} MB)")
    print("  PASS: Both files present")


def test_mmproj_map():
    """Verify _MMPROJ_MAP resolves model paths to mmproj paths."""
    print("\nTest 3: _MMPROJ_MAP lookup...")
    mmproj = _MMPROJ_MAP.get(QWEN3_VL_8B)
    assert mmproj is not None, "QWEN3_VL_8B not in _MMPROJ_MAP"
    assert mmproj == QWEN3_VL_8B_MMPROJ, f"mmproj mismatch: {mmproj} != {QWEN3_VL_8B_MMPROJ}"
    print(f"  PASS: {QWEN3_VL_8B.name} -> {mmproj.name}")


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

        # vision capability: mmproj MUST be loaded
        print("  Loading 'vision' (with mmproj)...")
        vision_backend = registry.get_backend("vision")
        assert vision_backend.is_loaded(), "Backend not loaded after get_backend('vision')"
        assert vision_backend.mmproj_path is not None, "vision capability must load mmproj"
        print(f"  PASS: {vision_backend.model_path.name} loaded with mmproj {vision_backend.mmproj_path.name}")
        registry.unload_all()
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
    print("Qwen3-VL-8B Abliterated Integration Tests")
    print("=" * 60)

    test_capability_map_routes()
    test_model_files_exist()
    test_mmproj_map()
    test_model_registry_loads()
    test_basic_chat()

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)
