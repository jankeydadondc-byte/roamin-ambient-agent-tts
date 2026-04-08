# Design: Plugin Outlet Infrastructure

## Context

The agent has a clean ToolRegistry with a `register()` method that already
accepts external tools. The AgentLoop creates and owns the registry. The
Control API already has plugin CRUD endpoints (backed by an empty list).

The goal is minimal scaffolding that turns "edit tools.py" into "drop a file."

## Goals

- Define what a plugin IS (contract)
- Auto-discover plugins without configuration
- Register plugin tools into the existing ToolRegistry
- Never crash the agent on a bad plugin

## Non-Goals

- Plugin sandboxing / isolation
- Plugin UI in the Control Panel
- Manifest validation beyond Protocol check
- Hot-reloading without restart
- Plugin dependency resolution

## Decisions

### D1: Protocol over ABC

Protocol (structural subtyping) requires no inheritance. A plugin author writes
a plain class with `name`, `on_load(registry)`, `on_unload()` -- if those exist,
it works. No `super().__init__()` ceremony. Uses `@runtime_checkable` for
isinstance checks that produce clear error messages.

### D2: `agent/plugins/` over project-root `plugins/`

Inside the `agent/` package namespace. Keeps imports natural
(`from agent.plugins import ...`), avoids polluting the project root.

### D3: Module-level loader function, not a class

The codebase favors module-level functions for utilities (see `paths.py`,
`config.py`). A `load_plugins(registry)` function is the simplest thing that
works. The ToolRegistry is already the state -- no need for another stateful
object.

### D4: Registry passed via `on_load(registry)` (explicit DI)

Plugins receive the registry as an argument. No globals, no singletons, no
import-time side effects. The AgentLoop already owns the registry instance.

### D5: Two discovery conventions

A module can export either:
- A `plugin` attribute (pre-built instance) -- simplest for trivial plugins
- A `Plugin` class -- for plugins that need `__init__` logic

The loader checks `plugin` first, then `Plugin`.

### D6: Underscore prefix to disable

Rename `foo.py` to `_foo.py` to disable. `__init__.py` is naturally excluded.
Discovery function skips all `_`-prefixed files. No config file needed.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Bad plugin crashes agent | try/except around import + on_load; log and skip |
| Two plugins register same tool name | Last-loaded wins (silent overwrite); future: add collision detection |
| Import-time side effects in plugins | try/except around importlib; plugin is skipped |
| Plugin can access all of Python | Accepted for now; sandboxing is Phase 5.1 (future) |

## Open Questions

None -- this is intentionally minimal. Complexity comes later when real plugins
exist and their needs drive the design.
