"""Tests for the plugin outlet infrastructure."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.core.tool_registry import ToolRegistry
from agent.plugins import PluginInfo, RoaminPlugin, discover_plugins, load_plugins, unload_plugins

# -- Protocol satisfaction tests --


class TestRoaminPluginProtocol:
    """Verify the Protocol contract validates correctly."""

    def test_valid_class_satisfies_protocol(self) -> None:
        """A class with name, on_load, on_unload satisfies RoaminPlugin."""

        class Good:
            name = "good"

            def on_load(self, registry: ToolRegistry) -> None:
                pass

            def on_unload(self) -> None:
                pass

        assert isinstance(Good(), RoaminPlugin)

    def test_missing_on_unload_fails_protocol(self) -> None:
        """A class missing on_unload does NOT satisfy RoaminPlugin."""

        class Bad:
            name = "bad"

            def on_load(self, registry: ToolRegistry) -> None:
                pass

        assert not isinstance(Bad(), RoaminPlugin)

    def test_missing_name_fails_protocol(self) -> None:
        """A class missing name does NOT satisfy RoaminPlugin."""

        class NoName:
            def on_load(self, registry: ToolRegistry) -> None:
                pass

            def on_unload(self) -> None:
                pass

        assert not isinstance(NoName(), RoaminPlugin)


# -- Discovery tests --


class TestDiscoverPlugins:
    """Verify filesystem discovery logic."""

    def test_skips_underscore_prefixed(self, tmp_path: object) -> None:
        """Files starting with _ are skipped (disabled convention)."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            td = Path(d)
            (td / "__init__.py").touch()
            (td / "_disabled.py").touch()
            (td / "active.py").touch()

            with patch("agent.plugins.PLUGIN_DIR", td):
                found = discover_plugins()

            assert found == ["active"]

    def test_returns_sorted_names(self) -> None:
        """Discovered plugins are returned in alphabetical order."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            td = Path(d)
            (td / "zebra.py").touch()
            (td / "alpha.py").touch()

            with patch("agent.plugins.PLUGIN_DIR", td):
                found = discover_plugins()

            assert found == ["alpha", "zebra"]


# -- Load/unload tests --


class TestLoadPlugins:
    """Verify end-to-end load with real and mock plugins."""

    def test_example_ping_loads_and_registers_tool(self) -> None:
        """The example_ping plugin registers a 'ping' tool that returns pong."""
        # Build a minimal registry without default tools
        reg = ToolRegistry.__new__(ToolRegistry)
        reg._tools = {}

        # Import and load the real example plugin
        from agent.plugins.example_ping import Plugin

        instance = Plugin()
        instance.on_load(reg)

        # Verify ping tool was registered and works
        assert "ping" in reg._tools
        result = reg._tools["ping"]["implementation"]({})
        assert result == {"success": True, "result": "pong"}

    def test_bad_module_skipped_gracefully(self) -> None:
        """A plugin that fails to import should not crash load_plugins."""
        reg = ToolRegistry.__new__(ToolRegistry)
        reg._tools = {}

        # Pretend we discovered a module that doesn't exist
        with patch("agent.plugins.discover_plugins", return_value=["nonexistent_module_xyz"]):
            loaded = load_plugins(reg)

        # Should return empty, not raise
        assert loaded == []

    def test_module_without_plugin_skipped(self) -> None:
        """A module that exists but has no Plugin class or plugin instance is skipped."""
        import types

        reg = ToolRegistry.__new__(ToolRegistry)
        reg._tools = {}

        # Create a fake module with no Plugin class
        fake_mod = types.ModuleType("agent.plugins.empty")

        with (
            patch("agent.plugins.discover_plugins", return_value=["empty"]),
            patch("importlib.import_module", return_value=fake_mod),
        ):
            loaded = load_plugins(reg)

        assert loaded == []


class TestUnloadPlugins:
    """Verify shutdown cleanup calls on_unload on each plugin."""

    def test_on_unload_called(self) -> None:
        """unload_plugins calls on_unload() on each loaded plugin."""
        mock_instance = MagicMock(spec=["name", "on_load", "on_unload"])
        mock_instance.name = "test"
        info = PluginInfo(name="test", module="agent.plugins.test", instance=mock_instance)

        unload_plugins([info])

        mock_instance.on_unload.assert_called_once()

    def test_on_unload_error_does_not_crash(self) -> None:
        """If on_unload raises, unload_plugins logs but does not crash."""
        mock_instance = MagicMock(spec=["name", "on_load", "on_unload"])
        mock_instance.name = "crashy"
        mock_instance.on_unload.side_effect = RuntimeError("boom")
        info = PluginInfo(name="crashy", module="agent.plugins.crashy", instance=mock_instance)

        # Should not raise
        unload_plugins([info])
