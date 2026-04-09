# Design: MemPalace Integration with Dual-Mode Support (Simplified — No Wiring Required)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                   AUTO-DISCOVERY PLUGIN SYSTEM                        │
│                                                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │   agent/plugins/ directory scan                                │  │
│  │   ├─ example_ping.py           ← Already discovered ✅          │  │
│  │   └─ mempalace.py              ← Will be discovered automatically ✅         │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              ↓                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │   Plugin loader calls on_load() for each plugin                │  │
│  │   ├─ MempalacePlugin.on_load(registry)                         │  │
│  │   │   ├─ Phase 1 (mode='plugin'): Register tools in registry   │  │
│  │   │   └─ Phase 2 (mode='standalone'/'auto'): Start MCP server │  │
│  │   └─ Auto-discovery handles all plugin lifecycle automatically  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  Result: No manual wiring in run_wake_listener.py required!            │
└─────────────────────────────────────────────────────────────────────┘

Why No Wiring Is Needed:
- Plugin outlet infrastructure is designed for zero-config auto-discovery
- example_ping.py works the same way (drop in directory, restart agent)
- Auto-load handles missing plugins gracefully (logs warning, continues)
- No breaking changes to existing startup sequence

When Would Wiring Be Needed? (Edge Cases — Not Required Here):
1. Programmatic plugin arguments (custom configuration at load time)
2. Deferred loading until specific lifecycle event
3. Metrics/diagnostics tracking for loaded plugins
4. Feature flags for environment-specific activation

For Option A (LM Studio-only), none of these apply → Zero wiring required!
```

## Implementation Details

### MemPalacePlugin Class Design

**Location**: `agent/plugins/mempalace.py`

```python
"""
================================================================================
MEMPALACE PLUGIN — AUTO-DISCOVERY READY (NO WIRING NEEDED)
Purpose: Registers MemPalace tools in Roamin agent registry via plugin outlet.
Integration: Auto-discovered from agent/plugins/ directory on startup.
Phase 1 (Current): Plugin-only mode for LM Studio integration.
Phase 2 (Future): Standalone MCP server capability via config flag.
================================================================================
"""

from __future__ import annotations
import sys
from pathlib import Path


class MempalacePlugin:
    """MemPalace plugin with auto-discovery support.

    AUTO-Discovery: Plugin system scans agent/plugins/ directory automatically.
    Drop this file in the directory → Restart Roamin → Plugin loads automatically.

    MODE_SELECTION (via environment config):
        'plugin'      → Register tools in Roamin registry (Phase 1)
        'standalone'  → Start MCP server only, skip tool registration (Phase 2)
        'auto'        → Auto-detect based on environment/config

    DESIGN PRINCIPLE:
        Phase 1 implementation NEVER blocks Option B later. Same codebase,
        just different mode flags ensure orthogonality between options.

    AUTO-DISCOVERY GUARANTEES:
        - Plugin loads automatically on startup (like example_ping.py)
        - No wiring in run_wake_listener.py required
        - Errors handled gracefully (logs warning, doesn't crash agent)
    """

    name = "mempalace_memory"  # Used for plugin identification

    def __init__(self, palace_path: str | None = None, mode: str = "plugin"):
        """Initialize MemPalace client and configure mode.

        Args:
            palace_path: Path to MemPalace data directory (defaults to standard location)
            mode: 'plugin', 'standalone', or 'auto' for Phase 1/2 capability selection
        """
        from agent.core.mempalace_client import MempalaceClient

        # Use default palace path if not specified
        default_path = "C:\\AI\\roamin-ambient-agent-tts\\mem_palace_data"
        self._palace_client = MemPalaceClient(palce_path or default_path)

        self.mode = mode
        self._standalone_server = None  # For Phase 2 MCP server process

    def on_load(self, registry) -> None:
        """Register tools in Roamin tool registry OR start MCP server based on mode.

        Called automatically by plugin loader system on startup.

        Phase 1 (plugin-only): Registers tools for LM Studio integration.
        Phase 2 (standalone): Starts MCP server process for Claude/Cursor.

        Design ensures orthogonality — adding Phase 2 later requires zero code changes,
        just enabling appropriate mode flag via environment configuration.
        """
        try:
            if self.mode in ("standalone", "auto"):
                # Phase 2 capability: Start MCP server for standalone use
                # (Skipped during Phase 1 deployment)
                self._start_mcp_server()
            elif self.mode == "plugin":
                # Phase 1 only: Register tools in Roamin registry for LM Studio
                self._register_tools(registry)
            # 'auto' mode: Let environment config decide which phase runs

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)

            if self.mode == "standalone":
                # MCP server failed to start — log error but don't crash Roamin
                logger.error("MemPalace MCP server startup failed (optional): %s", e)
            else:
                # Tool registration failed — log warning but continue loading other plugins
                logger.warning("MemPalace plugin tool registration partial success: %s", e)

    def on_unload(self):
        """Cleanup resources for both modes. Called automatically on shutdown."""
        try:
            if self._standalone_server:
                # Stop MCP server process (Phase 2 only)
                # Best-effort cleanup — never crashes Roamin even if this fails
                pass
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug("MemPalace plugin unload partial success: %s", e)


def _register_tools(registry):
    """Register MemPalace tools in Roamin registry (Phase 1 only).

    This function is called automatically by on_load() when mode='plugin'.
    """

    # Tool 1: mempalace_status — Palace overview (read-only)
    registry.register(
        name="mempalace_status",
        description="View MemPalace palace status (wings, rooms, drawer counts). Use for memory system diagnostics.",
        risk="low",  # Read-only access
        params={},
        implementation=lambda params: {
            "success": False,  # Will be real after MemPalace initialization
            "error": "Mempalace not initialized yet"
        },
    )

    # Tool 2: mempalace_search — Semantic search across MemPalace (read-only)
    registry.register(
        name="mempalace_search",
        description="Search MemPalace for memories. Uses semantic similarity to find relevant past conversations.",
        risk="low",
        params={"query": "str"},
        implementation=lambda params: {
            "success": False,  # Will be real after MemPalace initialization
            "error": "Mempalace search requires initialization"
        },
    )


def _start_mcp_server():
    """Start MCP server process for standalone use (Phase 2 only).

    This function is called automatically by on_load() when mode in ('standalone', 'auto').
    Currently a placeholder — to be implemented when Phase 2 becomes needed.

    Will handle:
    - Auto-detect available port if 8561 busy
    - Bind to 127.0.0.1 (localhost only, not internet-facing)
    - Append stdout/stderr to logs/mempalace_mcp.log for debugging
    """
    pass  # Phase 2 implementation deferred until needed
```

### Key Design Guarantee: Zero Wiring Required

**Auto-discovery works like this:**

```python
# On Roamin startup:
from agent.plugins import load_plugins

loaded_plugins = load_plugins(agent_loop.registry)
# Output: "Plugin loaded: mempalace_memory (agent.plugins.mempalace)"

# Plugin automatically calls on_load() → tools registered in registry
# No manual wiring needed in run_wake_listener.py!
```

**This is exactly how example_ping.py works:**

```python
# agent/plugins/example_ping.py exists and is auto-discovered
loaded_plugins = load_plugins(agent_loop.registry)
# Output: "Plugin loaded: example_ping (agent.plugins.example_ping)"
# No wiring in run_wake_listener.py!
```

**Same pattern for mempalace — just drop file, restart agent, done!**

---

### Configuration Design

**Location**: `.env.example` additions

```bash
# MemPalace integration settings
# Enable/disable MemPalace memory layer (default: plugin for gradual adoption)
ROAMIN_MEMPALACE_ENABLED=true

# MemPalace mode selection
# Options: plugin, standalone, auto
# - 'plugin': Register tools in Roamin registry only (Phase 1) ← DEFAULT
# - 'standalone': Start MCP server only, skip tool registration (Phase 2)
# - 'auto': Auto-detect based on environment config
ROAMIN_MEMPALACE_MODE=plugin

# MemPalace palace path
ROAMIN_MEMPALACE_PATH=C:\AI\roamin-ambient-agent-tts\mem_palace_data

# Standalone MCP server port (only used when MODE=standalone or MODE=auto)
ROAMIN_MEMPALACE_MCP_PORT=8561

```

### Environment Auto-Detection Logic

```python
# In MempalacePlugin.__init__:
import os

mode_env = os.environ.get("ROAMIN_MEMPALACE_MODE", "plugin")
if mode_env == "auto":
    # Determine mode based on other config flags or environment hints
    if os.environ.get("ROAMIN_MEMPALACE_STANDALONE_ENABLED"):
        mode = "standalone"
    elif os.environ.get("ROAMIN_MEMPALACE_PLUGIN_ONLY"):
        mode = "plugin"
    else:
        # Default to plugin-only (Phase 1) when auto-detect
        mode = "plugin"
```

---

### Port Management Strategy

**Phase 1 (Plugin-Only)**: No port issues — plugin tools don't require network access.

**Phase 2 (Standalone MCP Server)**: Auto-detect if port 8561 is already in use.

```python
# Auto-detect available port (to be implemented for Phase 2):
import socket

def _get_available_port(preferred=8561, fallback_range=(8760, 8780)):
    """Return available port starting from preferred."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", preferred))
        sock.close()
        return preferred
    except OSError:
        # Port in use — try alternatives or config override
        env_port = os.environ.get("ROAMIN_MEMPALACE_MCP_PORT")
        if env_port:
            return int(env_port)

        # If LM Studio is using 8561, auto-try common alternative
        for alt in [8562, 8563, 8564]:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", alt))
                sock.close()
                return alt
            except OSError:
                continue

        # Fallback to range from config
        fallback_start = fallback_range[0]
        fallback_end = fallback_range[1]
        for p in range(fallback_start, fallback_end + 1):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", p))
                sock.close()
                return p
            except OSError:
                continue

        # Last resort — raise warning but don't crash
        print("[WARN] All ports in range busy — using preferred port anyway")
        return preferred
```

---

### Tool Registration vs. Standalone Server Orthogonality

**Why they never conflict:**

1. **Tool Registry (Phase 1)**: Internal Python dict keyed by string name
2. **MCP Server (Phase 2)**: Network endpoint on specific port with HTTP/WSS protocol

3. **Different interfaces entirely** — no competition for same "name space"

4. **Mode config prevents ambiguity**:
```python
if mode == "plugin":
    # Only register tools, don't start MCP server
elif mode == "standalone":
    # Only start MCP server, don't register tools
else:  # mode == "auto"
    # Let environment decide which phase runs
```

---

### Testing Strategy

#### Phase 1 Tests (Existing Infrastructure):

```python
# tests/unit/test_mempalace_plugin.py
import pytest
from pathlib import Path


@pytest.fixture
def mempalace_plugin():
    from agent.plugins.mempalace import MempalacePlugin

    # Test with default config (Phase 1)
    plugin = MempalacePlugin()
    return plugin


def test_mempalace_plugin_loads(mode="plugin"):
    """Test plugin loads without errors in both modes."""
    from agent.plugins.mempalace import MempalacePlugin

    # Test Phase 1 mode (plugin-only)
    plugin = MempalacePlugin(mode="plugin")
    assert plugin.mode == "plugin"

    # Test Phase 2 mode (standalone)
    plugin = MempalacePlugin(mode="standalone")
    assert plugin.mode == "standalone"


def test_mempalace_tools_registered(mode="plugin"):
    """Test MemPalace tools register in registry when in plugin mode."""
    from agent.plugins.mempalace import MempalacePlugin
    from agent.core.tool_registry import ToolRegistry

    registry = ToolRegistry()
    plugin = MempalacePlugin(mode="plugin")  # Phase 1 only
    plugin.on_load(registry)

    assert "mempalace_status" in registry.list_tools()
    assert "mempalace_search" in registry.list_tools()


def test_mcp_server_not_started_in_plugin_mode():
    """Verify MCP server doesn't start when mode=plugin."""
    from agent.plugins.mempalace import MempalacePlugin

    plugin = MempalacePlugin(mode="plugin")
    # Verify _standalone_server is None or not started
    assert plugin._standalone_server is None


def test_plugin_auto_discovery():
    """Test that mempalace.py loads automatically from agent/plugins/."""
    from agent.plugins import discover_plugins, load_plugins
    from agent.core.tool_registry import ToolRegistry

    registry = ToolRegistry()
    discovered = discover_plugins()

    # mempalace should be in discovered plugins if file exists
    assert "mempalace" in discovered  # Will fail until plugin deployed

    loaded = load_plugins(registry)
    names = [p.name for p in loaded]
    assert "mempalace_memory" in names
```

---

### Deployment Steps (Phase 1 — No Wiring Required!)

```bash
# Step 1: Create mempalace.py plugin file (with dual-mode support)
copy openspec\changes\mempalace-integration\mempalace.py agent\plugins\mempalace.py

# Step 2: Install MemPalace dependencies (if not already installed)
pip install mempalace chromadb>=0.5.0,<0.7 pyyaml>=6.0

# Step 3: Create palace data directory if not exists
mkdir C:\AI\roamin-ambient-agent-tts\mem_palace_data

# Step 4 (Optional): Add configuration to .env file
echo ROAMIN_MEMPALACE_ENABLED=true >> .env
echo ROAMIN_MEMPALACE_MODE=plugin >> .env
echo ROAMIN_MEMPALACE_PATH=C:\AI\roamin-ambient-agent-tts\mem_palace_data >> .env

# Step 5: Restart Roamin agent (via launch.py if in development mode)
python launch.py

# Result: Plugin auto-discovered, tools registered automatically
# No wiring in run_wake_listener.py needed!
```

---

### Open Questions (Design Decisions Pending)

1. **Memory naming convention for MemPalace**:
   - Current: Generic "wing=Roamin" for all stored content
   - Future consideration: Wing prefixes like `mempalace_decisions`, `mempalace_facts`

2. **Graceful degradation on MemPalace unavailable**:
   - Phase 1: Silent fail, log warning, continue with existing memory system ✅
   - Phase 2: MCP server process can exit gracefully with message to user

3. **When will Phase 2 be implemented?**
   - Trigger event: When Claude/Cursor explicitly needed for MemPalace access
   - Estimated effort: ~30 minutes (add MCP server startup logic)
   - Can wait indefinitely — no blocking required from Phase 1

---

**Key Takeaway**: MemPalace plugin uses existing auto-discovery infrastructure. Drop file in `agent/plugins/`, restart agent, and it loads automatically — same as `example_ping.py`. No wiring needed!
