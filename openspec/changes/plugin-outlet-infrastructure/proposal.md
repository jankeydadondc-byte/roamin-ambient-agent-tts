# Proposal: Plugin Outlet Infrastructure

## Why

Priority 5 (Plugin System Foundation) is unstarted. No plugins exist yet, and
the full system (sandboxing, lifecycle management, discovery UI) is premature.

However, building the **outlet now** means that when a plugin IS needed, the
workflow is: drop a `.py` file in `agent/plugins/`, restart Roamin, done.
No config editing, no manifest writing, no registration ceremony.

## What Changes

1. **RoaminPlugin Protocol** -- defines the contract (name, on_load, on_unload)
2. **Auto-discovery loader** -- scans `agent/plugins/` for valid plugin modules
3. **Startup wiring** -- loads plugins into the real ToolRegistry at boot
4. **Example plugin** -- `example_ping.py` adds a harmless `ping` tool as proof

## Scope

- Outlet only -- no sandboxing, no UI integration, no manifest validation
- ~175 lines of new code, ~9 lines of edits to existing files
- No new dependencies
- No behavior changes to existing functionality

## Capabilities

| Capability | Status |
|-----------|--------|
| Define plugin contract | New |
| Auto-discover plugins from directory | New |
| Register plugin tools into ToolRegistry | New |
| Disable plugins via filename convention | New |
| Plugin lifecycle hooks (load/unload) | New |

## Impact

| File | Change |
|------|--------|
| `agent/plugins/__init__.py` | NEW -- contract + loader |
| `agent/plugins/example_ping.py` | NEW -- reference plugin |
| `tests/test_plugin_loader.py` | NEW -- tests |
| `agent/core/agent_loop.py` | +4 lines -- expose registry property |
| `run_wake_listener.py` | +5 lines -- wire plugin loading at startup |
