# Plugin Development Guide

This guide explains how to write and deploy a plugin for Roamin. Plugins are auto-discovered
and require no wiring — just drop a `.py` file in `agent/plugins/` and it loads on startup.

---

## What Is a Plugin?

A plugin is a Python module that:

1. Defines a class named `Plugin`
2. Implements `on_load(registry)` to register one or more tools
3. Optionally implements `on_unload()` for cleanup
4. Is placed in the `agent/plugins/` directory
5. Is automatically discovered and loaded on agent startup

**No wiring required.** The plugin loader scans `agent/plugins/` at runtime, imports
each non-underscore `.py` file, instantiates `Plugin()`, and calls `on_load()`. This
is how `example_ping.py` and `mempalace.py` work.

---

## Minimal Plugin Template

Here's the smallest working plugin, fully annotated:

```python
# agent/plugins/my_first_plugin.py
"""My first plugin — does something useful."""

class Plugin:
    """Plugin class. Loader looks for this exact name."""

    name = "my_first_plugin"  # Unique identifier, snake_case

    def on_load(self, registry) -> None:
        """Called once on agent startup.

        Args:
            registry: ToolRegistry instance. Call registry.register() to add tools.
        """
        registry.register(
            name="hello_world",           # What LM Studio sees when calling the tool
            description="Say hello to the user",  # Shown in the planner
            risk="low",                   # Approval required? (see Risk Levels below)
            params={"name": "str"},       # Parameter schema: key → type
            implementation=self._hello,   # Callable that executes the tool
        )

    def on_unload(self) -> None:
        """Called when agent shuts down. Cleanup connections, stop threads, etc.

        Optional — if you don't need cleanup, omit this method.
        """
        pass

    def _hello(self, params: dict) -> dict:
        """Execute the tool. Must return a dict.

        Args:
            params: dict with keys matching those in registry.register(params=...)

        Returns:
            dict with a "result" key (or "error" on failure).
        """
        name = params.get("name", "friend")
        return {"result": f"Hello, {name}!"}
```

**That's all you need.** Save as `agent/plugins/my_first_plugin.py` and restart Roamin.

---

## Registering Tools

The `registry.register()` call takes these arguments:

| Arg | Type | Example | Notes |
|---|---|---|---|
| `name` | str | `"my_tool"` | Unique tool ID. LM Studio calls it by this name. |
| `description` | str | `"Does X and Y"` | Shown to the planner. Keep it one sentence. |
| `risk` | str | `"low"` | One of `low`, `medium`, `high` — see table below. |
| `params` | dict | `{"query": "str", "limit": "int"}` | Parameter schema. Key is param name, value is type hint. |
| `implementation` | callable | `self._my_impl` | Function to call. Must accept `params: dict` and return `dict`. |

### Risk Levels

| Level | Behaviour | When to Use |
|---|---|---|
| `low` | Tool executes immediately, no approval needed. | Read-only queries (search, status, list). |
| `medium` | Tool executes immediately but is logged to `logs/audit.log`. | Modifying operations (write, enable, disable). |
| `high` | Tool is blocked. Control Panel shows approval toast. Waits for user approve/deny via UI. | Dangerous ops (delete, reset, install unsigned code). |

Example:
```python
registry.register(
    name="delete_file",
    description="Delete a file from disk",
    risk="high",  # ← User must approve via Control Panel
    params={"path": "str"},
    implementation=self._delete_file,
)
```

---

## Tool Implementation (the Callable)

Your `implementation` callable must:

1. Accept exactly one argument: `params: dict`
2. Return exactly one type: `dict`
3. Always return a dict with either `"result"` (success) or `"error"` (failure)

Example:
```python
def _search(self, params: dict) -> dict:
    query = params.get("query", "")

    if not query:
        return {"error": "query parameter required"}

    try:
        results = self.search_backend(query)
        return {"result": results}
    except Exception as e:
        return {"error": str(e)}
```

**Do not raise exceptions.** Return `{"error": "..."}` instead. This lets the agent
handle the error gracefully (retry, fallback, etc.) instead of crashing.

---

## Multiple Tools in One Plugin

Plugins can register multiple tools:

```python
class Plugin:
    name = "my_multi_tool_plugin"

    def on_load(self, registry) -> None:
        registry.register(
            name="tool_1",
            description="First tool",
            risk="low",
            params={},
            implementation=self._tool_1,
        )
        registry.register(
            name="tool_2",
            description="Second tool",
            risk="low",
            params={"input": "str"},
            implementation=self._tool_2,
        )

    def _tool_1(self, params: dict) -> dict:
        return {"result": "tool 1 output"}

    def _tool_2(self, params: dict) -> dict:
        return {"result": f"tool 2 input was: {params['input']}"}
```

---

## Handling Errors and Unavailability

If your plugin requires a library or service that might not be available:

```python
class Plugin:
    name = "external_service_plugin"

    def on_load(self, registry) -> None:
        try:
            import external_service  # Might not be installed
            self.service = external_service.Client()
        except ImportError:
            self.service = None

        registry.register(
            name="call_service",
            description="Call external service",
            risk="low",
            params={"data": "str"},
            implementation=self._call,
        )

    def _call(self, params: dict) -> dict:
        if self.service is None:
            return {"error": "external_service not installed"}

        try:
            result = self.service.process(params["data"])
            return {"result": result}
        except Exception as e:
            return {"error": f"service error: {str(e)}"}
```

This way, the plugin loads cleanly even if the dependency is missing. The tool just
returns a helpful error when called.

---

## Running Subprocesses

If your tool needs to run another program (like `mempalace status`):

```python
import subprocess
import sys

class Plugin:
    name = "subprocess_plugin"

    def on_load(self, registry) -> None:
        registry.register(
            name="run_command",
            description="Run a shell command",
            risk="high",  # Commands are dangerous!
            params={"cmd": "str"},
            implementation=self._run,
        )

    def _run(self, params: dict) -> dict:
        cmd = params.get("cmd", "")
        if not cmd:
            return {"error": "cmd parameter required"}

        try:
            result = subprocess.run(
                [sys.executable, "-m", "some_module", cmd],
                capture_output=True,
                text=True,
                timeout=30,  # ← Always set timeout to prevent hangs
            )
            if result.returncode != 0:
                return {"error": result.stderr}
            return {"result": result.stdout}
        except subprocess.TimeoutExpired:
            return {"error": "command timed out after 30 seconds"}
        except Exception as e:
            return {"error": str(e)}
```

**Always use `timeout=`** to prevent the agent from hanging indefinitely.

---

## Disabling a Plugin Without Deleting It

To temporarily disable a plugin without removing the file, rename it with a leading underscore:

```bash
# Disable
mv agent/plugins/my_plugin.py agent/plugins/_my_plugin.py

# Enable
mv agent/plugins/_my_plugin.py agent/plugins/my_plugin.py
```

The plugin loader skips files starting with `_`, so `_my_plugin.py` is never loaded.

---

## Testing Your Plugin

Write a simple test to verify your plugin loads and works:

```python
# test_my_plugin.py — save this anywhere, run with pytest

from agent.plugins.my_first_plugin import Plugin
from agent.core.tool_registry import ToolRegistry

def test_plugin_loads():
    """Plugin instantiates without error."""
    plugin = Plugin()
    assert plugin.name == "my_first_plugin"

def test_tools_register():
    """Tools register into the registry."""
    registry = ToolRegistry()
    plugin = Plugin()
    plugin.on_load(registry)

    tools = registry.list_tools()
    assert "hello_world" in tools

def test_hello_world_tool():
    """Tool executes and returns expected result."""
    registry = ToolRegistry()
    plugin = Plugin()
    plugin.on_load(registry)

    result = registry.execute("hello_world", {"name": "Alice"})
    assert result["result"] == "Hello, Alice!"

def test_hello_world_missing_param():
    """Tool handles missing params gracefully."""
    registry = ToolRegistry()
    plugin = Plugin()
    plugin.on_load(registry)

    result = registry.execute("hello_world", {})
    assert result["result"] == "Hello, friend!"  # Falls back to "friend"
```

Run it:
```powershell
pytest test_my_plugin.py -v
```

---

## Real Examples to Read

Learn from existing plugins:

### `agent/plugins/example_ping.py`

Minimal working plugin. Shows:
- Basic tool structure
- Simple parameter handling
- Return format

**Read if:** You want the absolute simplest starting point.

### `agent/plugins/mempalace.py`

Production plugin. Shows:
- ImportError handling (graceful degradation if mempalace not installed)
- Subprocess management (`subprocess.Popen` for MCP server)
- Multiple tools in one plugin (status + search)
- Mode-based behaviour (`if _MODE in (...)`)
- Proper logging and error messages

**Read if:** You need to understand how to handle complex dependencies or run subprocesses.

---

## Common Patterns

### Pattern: Caching/State

```python
class Plugin:
    name = "cached_plugin"

    def __init__(self):
        self._cache = {}

    def on_load(self, registry) -> None:
        registry.register(
            name="fetch_and_cache",
            description="Fetch data and cache it",
            risk="low",
            params={"key": "str"},
            implementation=self._fetch,
        )

    def _fetch(self, params: dict) -> dict:
        key = params.get("key")

        if key in self._cache:
            return {"result": self._cache[key], "cached": True}

        data = self.expensive_operation(key)
        self._cache[key] = data
        return {"result": data, "cached": False}
```

### Pattern: Configuration from Environment

```python
import os

class Plugin:
    name = "configurable_plugin"

    def __init__(self):
        self.api_key = os.environ.get("MY_PLUGIN_API_KEY")

    def on_load(self, registry) -> None:
        if not self.api_key:
            # Warn but don't crash
            import logging
            logging.warning("MY_PLUGIN_API_KEY not set — plugin tools will fail")

        registry.register(
            name="call_api",
            description="Call external API",
            risk="low",
            params={"path": "str"},
            implementation=self._call,
        )

    def _call(self, params: dict) -> dict:
        if not self.api_key:
            return {"error": "MY_PLUGIN_API_KEY environment variable not set"}

        # Use self.api_key to authenticate
        return {"result": "success"}
```

---

## Checklist Before Shipping

- [ ] Plugin file is in `agent/plugins/` and named `*.py` (not `_*.py`)
- [ ] Plugin class is named exactly `Plugin`
- [ ] `on_load(registry)` is implemented
- [ ] Each tool has `name`, `description`, `risk`, `params`, `implementation`
- [ ] Tool implementation returns `{"result": ...}` or `{"error": ...}` (always a dict)
- [ ] All subprocesses have `timeout=` set
- [ ] ImportErrors are caught and handled gracefully
- [ ] Plugin loads cleanly: `python -c "from agent.plugins.my_plugin import Plugin; Plugin().on_load(None)"` doesn't crash
- [ ] At least one test passes

---

## Next Steps

1. Copy the minimal template above
2. Replace `my_first_plugin` with your plugin name
3. Add your tools and implementations
4. Test with the test pattern shown above
5. Drop in `agent/plugins/` and restart the agent
6. Ask Roamin to use your tool — it should appear in the planner's tool list

---

## Questions?

- **How do tools get called?** → The planner sees all registered tools, picks one,
  passes parameters, your `implementation` callable runs.
- **Can I call other tools?** → No direct way. If you need shared functionality, put
  it in a separate module and import it.
- **Can a tool be async?** → No. Keep implementations synchronous for now. Blocking
  operations should use subprocess with timeout.
- **What if my tool needs config?** → Use environment variables (`.env`) and read them
  in `__init__()`.
