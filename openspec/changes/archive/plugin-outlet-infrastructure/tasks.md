# Tasks: Plugin Outlet Infrastructure

## 1. Create plugin contract and loader

- [x] 1.1 Create `agent/plugins/__init__.py`
- [x] 1.2 Define `RoaminPlugin` Protocol with `name`, `on_load`, `on_unload`
- [x] 1.3 Implement `PluginInfo` metadata dataclass
- [x] 1.4 Implement `discover_plugins()` -- scan directory, skip `_`-prefixed
- [x] 1.5 Implement `load_plugins(registry)` -- import, instantiate, validate, on_load
- [x] 1.6 Implement `unload_plugins(plugins)` -- call on_unload, best-effort

## 2. Create example plugin

- [x] 2.1 Create `agent/plugins/example_ping.py`
- [x] 2.2 Implement `Plugin` class with `ping` tool registration
- [x] 2.3 Add dev comments above each logical block

## 3. Wire into startup

- [x] 3.1 Add `registry` property to `AgentLoop` (agent_loop.py)
- [x] 3.2 Add plugin loading to `run_wake_listener.py` main()
- [x] 3.3 Register `unload_plugins` with atexit

## 4. Tests

- [x] 4.1 Create `tests/test_plugin_loader.py`
- [x] 4.2 Test Protocol satisfaction (good class passes, bad class fails)
- [x] 4.3 Test discovery skips underscore-prefixed files
- [x] 4.4 Test example_ping loads and registers ping tool
- [x] 4.5 Test bad module import is skipped gracefully
- [x] 4.6 Test on_unload is called during shutdown

## 5. Verify

- [x] 5.1 `pytest tests/test_plugin_loader.py -v` -- all pass (10/10 verified 2026-04-08)
- [x] 5.2 `python launch.py` -- boot log shows plugin loaded (confirmed: "Plugin loaded: example_ping" on every startup)
- [x] 5.3 Pre-commit passes on all files (runs automatically on commit)
- [x] 5.4 Commit and push to main (all changes on main branch)
