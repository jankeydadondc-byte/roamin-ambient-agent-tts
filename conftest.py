"""Root conftest.py — ensures venv packages take priority over stub directories,
and skips @pytest.mark.integration tests unless -m integration is explicitly requested.

Test stubs live in tests/_stubs/ (not the project root) so they never shadow
real venv packages when running scripts directly (run_wake_listener.py etc.).
The stubs dir is appended at the END of sys.path so it only activates if the
real package is absent from the venv.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.resolve()
_STUBS = _ROOT / "tests" / "_stubs"

# Remove project-root entries so the root itself isn't at sys.path[0].
# Python prepends '' (cwd) when run with -m; remove that too.
_cleaned = []
for _p in sys.path:
    try:
        _resolved = Path(_p).resolve() if _p else _ROOT
    except Exception:
        _resolved = None
    if _resolved != _ROOT:
        _cleaned.append(_p)

# Re-add project root at the END, then stubs as absolute last resort.
_cleaned.append(str(_ROOT))
if str(_STUBS) not in _cleaned:
    _cleaned.append(str(_STUBS))
sys.path[:] = _cleaned

# Invalidate any stub imports that may have been cached before conftest ran.
for _mod in list(sys.modules):
    if _mod in ("fastapi", "chromadb", "numpy") or any(
        _mod.startswith(f"{pkg}.") for pkg in ("fastapi", "chromadb", "numpy")
    ):
        del sys.modules[_mod]


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.integration tests unless -m integration was requested."""
    if config.option.markexpr:
        return
    skip_integration = pytest.mark.skip(reason="integration test — run with: pytest -m integration")
    for item in items:
        if item.get_closest_marker("integration"):
            item.add_marker(skip_integration)
