"""Plugin outlet -- contract and auto-discovery for Roamin plugins.

Drop a .py file in this directory to add a plugin. It auto-loads on startup.
Rename to _foo.py to disable. See example_ping.py for the pattern.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Protocol, runtime_checkable

from agent.core.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# Root directory for plugin discovery (this package's directory)
PLUGIN_DIR = Path(__file__).parent


# -- Protocol: defines the shape of a valid plugin (duck typing, no inheritance) --
@runtime_checkable
class RoaminPlugin(Protocol):
    """Contract for a Roamin plugin.

    Any class that implements these attributes/methods is a valid plugin.
    No inheritance required -- just duck typing via Protocol.
    """

    name: str

    def on_load(self, registry: ToolRegistry) -> None:
        """Called once at startup. Register tools, set up state."""
        ...

    def on_unload(self) -> None:
        """Called on shutdown or plugin removal. Clean up resources."""
        ...


# -- PluginInfo: metadata wrapper returned after a successful load --
class PluginInfo:
    """Metadata about a loaded plugin (returned to callers for tracking)."""

    def __init__(self, name: str, module: str, instance: RoaminPlugin) -> None:
        self.name = name
        self.module = module
        self.instance = instance


# -- discover_plugins: scan this directory for non-underscore .py files --
def discover_plugins() -> list[str]:
    """Return module names of discoverable plugins (e.g. ['example_ping']).

    Skips _-prefixed files (disabled plugins) and __init__.py.
    """
    found: list[str] = []
    for path in sorted(PLUGIN_DIR.glob("*.py")):
        # Skip private/disabled modules (underscore prefix convention)
        if path.stem.startswith("_"):
            continue
        found.append(path.stem)
    return found


# -- load_plugins: import, instantiate, validate, and on_load each plugin --
def load_plugins(registry: ToolRegistry) -> list[PluginInfo]:
    """Discover, import, instantiate, and load all plugins.

    Returns list of successfully loaded PluginInfo objects.
    Errors are logged and skipped -- a bad plugin never crashes the agent.
    """
    loaded: list[PluginInfo] = []

    for module_name in discover_plugins():
        fqn = f"agent.plugins.{module_name}"

        # Try importing the plugin module
        try:
            mod = importlib.import_module(fqn)
        except Exception:
            logger.exception("Plugin '%s': import failed", module_name)
            continue

        # Look for a pre-built `plugin` instance or a `Plugin` class to instantiate
        instance: RoaminPlugin | None = getattr(mod, "plugin", None)
        if instance is None:
            cls = getattr(mod, "Plugin", None)
            if cls is not None:
                # Instantiate the Plugin class
                try:
                    instance = cls()
                except Exception:
                    logger.exception("Plugin '%s': instantiation failed", module_name)
                    continue

        # Skip modules that don't export a valid plugin
        if instance is None:
            logger.warning(
                "Plugin '%s': no `plugin` instance or `Plugin` class found -- skipped",
                module_name,
            )
            continue

        # Validate the plugin satisfies the RoaminPlugin protocol
        if not isinstance(instance, RoaminPlugin):
            logger.warning(
                "Plugin '%s': does not satisfy RoaminPlugin protocol " "(needs name, on_load, on_unload) -- skipped",
                module_name,
            )
            continue

        # Call on_load to let the plugin register its tools
        try:
            instance.on_load(registry)
            loaded.append(PluginInfo(name=instance.name, module=fqn, instance=instance))
            logger.info("Plugin loaded: %s (%s)", instance.name, fqn)
        except Exception:
            logger.exception("Plugin '%s': on_load() failed", module_name)
            continue

    return loaded


# -- unload_plugins: call on_unload() on each loaded plugin (best-effort) --
def unload_plugins(plugins: list[PluginInfo]) -> None:
    """Call on_unload() on all loaded plugins. Best-effort, never crashes."""
    for info in plugins:
        try:
            info.instance.on_unload()
            logger.info("Plugin unloaded: %s", info.name)
        except Exception:
            logger.exception("Plugin '%s': on_unload() failed", info.name)
