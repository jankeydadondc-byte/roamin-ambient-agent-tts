"""Tests for single-instance guard — named mutex in run_wake_listener.py."""

import sys
from unittest.mock import MagicMock, patch

# run_wake_listener.py imports 'keyboard' at module level (not installed in test venv).
# Stub it out before any import of the module so tests can run without the package.
_STUBS = {
    "keyboard": MagicMock(),
    "agent.core.model_sync": MagicMock(),
    "agent.core.agent_loop": MagicMock(),
    "agent.core.model_router": MagicMock(),
    "agent.core.voice.stt": MagicMock(),
    "agent.core.voice.tts": MagicMock(),
    "agent.core.voice.wake_listener": MagicMock(),
}


def _load_rwl():
    """Import run_wake_listener with heavy dependencies stubbed out."""
    with patch.dict(sys.modules, _STUBS):
        import importlib

        import run_wake_listener as rwl

        importlib.reload(rwl)
    return rwl


class TestNamedMutex:
    """Verify _acquire_single_instance_mutex() under mocked Win32 calls."""

    def _run(self, last_error: int, handle: int = 42):
        """Call _acquire_single_instance_mutex with a controlled kernel32 mock."""
        mock_k32 = MagicMock()
        mock_k32.CreateMutexW.return_value = handle
        mock_k32.GetLastError.return_value = last_error

        with patch.dict(sys.modules, _STUBS):
            import run_wake_listener as rwl

            with patch.object(rwl.ctypes, "windll") as mock_windll:
                mock_windll.kernel32 = mock_k32
                result = rwl._acquire_single_instance_mutex()

        return result, mock_k32

    def test_first_instance_returns_handle(self):
        """GetLastError=0 → handle returned, CloseHandle NOT called."""
        result, k32 = self._run(last_error=0, handle=42)
        assert result == 42
        k32.CloseHandle.assert_not_called()

    def test_already_running_returns_none(self):
        """GetLastError=183 (ERROR_ALREADY_EXISTS) → None returned."""
        result, k32 = self._run(last_error=183, handle=99)
        assert result is None

    def test_already_running_closes_handle(self):
        """When another instance holds the mutex, the duplicate handle is closed."""
        result, k32 = self._run(last_error=183, handle=99)
        k32.CloseHandle.assert_called_once_with(99)

    def test_mutex_name_has_global_prefix(self):
        """Mutex name must start with 'Global\\' to work across user sessions."""
        with patch.dict(sys.modules, _STUBS):
            import run_wake_listener as rwl
        assert rwl._MUTEX_NAME.startswith("Global\\"), (
            f"Mutex name '{rwl._MUTEX_NAME}' must start with 'Global\\\\' "
            "to prevent duplicate instances across Windows session boundaries"
        )


class TestMainExitsOnDuplicateMutex:
    """Verify main() exits when _acquire_single_instance_mutex signals a duplicate."""

    def test_main_exits_when_mutex_unavailable(self):
        """main() calls sys.exit(0) when mutex returns None — stops before any startup work."""
        import pytest

        with patch.dict(sys.modules, _STUBS):
            import run_wake_listener as rwl

            with patch.object(rwl, "_acquire_single_instance_mutex", return_value=None):
                with patch.object(rwl, "_prune_log"):
                    with patch("builtins.open", MagicMock()):
                        # side_effect=SystemExit(0) makes the exit real — prevents main()
                        # from continuing past the guard and spawning subprocesses.
                        with patch("sys.exit", side_effect=SystemExit(0)):
                            with pytest.raises(SystemExit) as exc_info:
                                rwl.main()
                            assert exc_info.value.code == 0
