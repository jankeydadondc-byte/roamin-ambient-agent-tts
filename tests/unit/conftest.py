"""
Unit test conftest — stubs heavy/unavailable packages so unit tests
can import agent modules without needing the full runtime environment.

Packages stubbed here:
  - chromadb          (used by memory_search.py)
  - keyboard          (used by wake_listener.py)
  - llama_cpp         (used by llama_backend.py)
  - psutil            (used by resource_monitor.py — already optional, but stub for safety)
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

_STUBS = [
    "chromadb",
    "chromadb.config",
    "keyboard",
    "llama_cpp",
    # psutil NOT stubbed — resource_monitor tests mock it themselves
]

for _mod in _STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
