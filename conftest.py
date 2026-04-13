"""Root conftest.py — ensures venv packages take priority over local stub directories,
and skips @pytest.mark.integration tests unless -m integration is explicitly requested.

chromadb/, fastapi/, numpy/ exist in the project root as test stubs. With
--import-mode=importlib (pytest.ini) these are no longer prepended, but we keep the
sys.modules invalidation here as a belt-and-suspenders guard.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.resolve()

# Remove all sys.path entries that resolve to the project root, then re-add at end.
# Python prepends '' (cwd) to sys.path when run with -m, which causes local stub
# directories (chromadb/, fastapi/, numpy/) to shadow real venv packages.
_cleaned = []
for _p in sys.path:
    try:
        _resolved = Path(_p).resolve() if _p else _ROOT
    except Exception:
        _resolved = None
    if _resolved != _ROOT:
        _cleaned.append(_p)
_cleaned.append(str(_ROOT))
sys.path[:] = _cleaned

# Invalidate any stub imports that may have been cached before conftest ran.
for _mod in list(sys.modules):
    if _mod == "fastapi" or _mod.startswith("fastapi."):
        del sys.modules[_mod]
    if _mod == "chromadb" or _mod.startswith("chromadb."):
        del sys.modules[_mod]
    if _mod == "numpy" or _mod.startswith("numpy."):
        del sys.modules[_mod]


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.integration tests unless -m integration was requested."""
    # If the user explicitly filtered with -m (e.g. -m integration), respect it.
    if config.option.markexpr:
        return
    skip_integration = pytest.mark.skip(reason="integration test — run with: pytest -m integration")
    for item in items:
        if item.get_closest_marker("integration"):
            item.add_marker(skip_integration)
