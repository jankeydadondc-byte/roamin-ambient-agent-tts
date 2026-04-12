# Tasks: MemPalace Integration Implementation (Auto-Discovery Approach — No Wiring Required!)

## Phase 1 — Plugin-Only ✅ COMPLETE

### Key Design Principle: Auto-Discovery, Zero Wiring Needed!

Unlike the previous thinking, **NO wiring into `run_wake_listener.py` is required!**

The existing plugin outlet infrastructure handles auto-discovery automatically:
- Scans `agent/plugins/` directory for all non-underscore `.py` files
- Loads and instantiates each plugin via duck typing
- Calls `on_load(registry)` to register tools
- Handles errors gracefully (bad plugins don't crash agent)

This is exactly how `example_ping.py` works!

```python
# What happens automatically when you add mempalace.py to agent/plugins/:
agent/plugins/
├── example_ping.py          ← Already discovered ✅
└── mempalace.py             ← Will be discovered automatically ✅

Plugin loader scans directory on startup → auto-discovery handles everything!
No manual wiring in run_wake_listener.py needed.
```

---

### Task 1.1: Create Plugin Module (Simplified — Auto-Discovery Ready)

**File**: `agent/plugins/mempalace.py`
**Effort**: ~45 minutes
**Status**: ✅ COMPLETE

**Acceptance Criteria**:
- [x] Plugin file created with dual-mode support (plugin/standalone/auto modes)
- [x] Tool registration logic implemented for Phase 1 (register tools in registry when mode='plugin')
- [x] Zero import errors or syntax issues
- [x] Code includes dev comments explaining each section
- [x] Plugin handles MemPalace unavailable gracefully (logs warning, doesn't crash)
- [x] NO manual wiring in run_wake_listener.py — auto-discovery handles loading!

**Notes**: Design doc had several bugs corrected — class named `Plugin` (not `MempalacePlugin`),
used real `search_memories()` API (no `MempalaceClient`), `n_results` param (not `k`), `--palace`
flag placed before subcommand in CLI call. chromadb 1.5.5 used (0.6.3 broken on Python 3.14).

---

### Task 1.2: Create MemPalace Client Module

**Status**: ✅ NOT NEEDED — Design doc artifact superseded.

The design doc proposed a `mempalace_client.py` wrapper module, but the real mempalace
package exposes `from mempalace.searcher import search_memories` directly. The plugin calls
the package API inline — no intermediate wrapper needed.

**Dependencies installed**:
```
mempalace (git+https://github.com/jankeydadondc-byte/mempalace @ 71736a3)
chromadb 1.5.5 (0.6.3 incompatible with Python 3.14)
pyyaml (already present)
```

---

### Task 1.3: Create Palace Data Directory

**File**: `C:\AI\roamin-ambient-agent-tts\mem_palace_data`
**Status**: ✅ COMPLETE

**Acceptance Criteria**:
- [x] Directory exists at specified path
- [x] Palace initialized — `mempalace init` + `mempalace mine` run successfully
- [x] 1590 drawers filed across 172 files (all project code + docs indexed)
- [x] `mempalace.yaml` config created at project root
- [x] `mem_palace_data/` and generated files added to `.gitignore`

---

### Task 1.4: Update Configuration Examples

**File**: `.env.example`
**Lines to Add**: ~10 lines
**Effort**: ~5 minutes
**Status**: ✅ COMPLETE

**Changes Required**:
```bash
# Add these lines to .env.example at end of file (before blank line)

# MemPalace integration settings
# Enable/disable MemPalace memory layer (default: plugin for gradual adoption)
ROAMIN_MEMPALACE_ENABLED=true

# MemPalace mode selection
# Options: plugin, standalone, auto
# - 'plugin': Register tools in Roamin registry only (Phase 1)
# - 'standalone': Start MCP server only, skip tool registration (Phase 2)
# - 'auto': Auto-detect based on environment config
ROAMIN_MEMPALACE_MODE=plugin

# MemPalace palace path
ROAMIN_MEMPALACE_PATH=C:\AI\roamin-ambient-agent-tts\mem_palace_data

# Standalone MCP server port (only used when MODE=standalone or MODE=auto)
ROAMIN_MEMPALACE_MCP_PORT=8561

```

---

### Task 1.5: Create Openspec Documentation

**Files**:
- `.openspec.yaml` ✅ CREATED
- `proposal.md` ✅ CREATED
- `design.md` ✅ UPDATED (removed wiring requirement)
- `tasks.md` ⏳ CURRENT FILE
- `README.md` ✅ CREATED

**Status**: ✅ COMPLETE

---

## Phase 1 Verification Checklist

### Static Analysis

```bash
# Verify plugin file compiles cleanly
py_compile agent/plugins/mempalace.py
py_compile agent/core/mempalace_client.py

# Flake8 linting (max line length 120 per project rules)
flake8 agent/plugins/mempalace.py --max-line-length=120
flake8 agent/core/mempalace_client.py --max-line-length=120

# Mypy type checking (optional, recommended for production readiness)
mypy agent/plugins/mempalace.py --ignore-missing-imports
mypy agent/core/mempalace_client.py --ignore-missing-imports
```

### Dynamic Validation

**Test 1: Plugin Auto-Discovery (Verify No Wiring Needed)**
```python
# After copying mempalace.py to agent/plugins/ directory:
from agent.plugins import discover_plugins, load_plugins
from agent.core.tool_registry import ToolRegistry

registry = ToolRegistry()
discovered = discover_plugins()
print(f"Discovered plugins: {discovered}")

# Should show: ['example_ping', 'mempalace'] (no manual wiring needed!)
loaded = load_plugins(registry)
names = [p.name for p in loaded]
print(f"Loaded plugin names: {names}")
assert "mempalace_memory" in names  # Auto-discovered!
```

**Test 2: Tool Registration**
```python
# Verify tools register automatically when plugin loads
from agent.core.tool_registry import ToolRegistry
from agent.plugins.mempalace import MempalacePlugin

registry = ToolRegistry()
plugin = MempalacePlugin("C:\\AI\\roamin-ambient-agent-tts\\mem_palace_data", mode="plugin")
plugin.on_load(registry)

print(f"Registered tools: {registry.list_tools()}")
assert "mempalace_status" in registry.list_tools()
assert "mempalace_search" in registry.list_tools()
```

**Test 3: Graceful Degradation (MemPalace Not Installed)**
```python
# MemPalace not installed — should handle gracefully
from agent.core.mempalace_client import MempalaceClient

try:
    client = MempalaceClient("C:\\AI\\roamin-ambient-agent-tts\\mem_palace_data")
except Exception as e:
    print(f"Expected error on MemPalace not installed: {e}")
    # Verify doesn't crash agent, just logs warning
```

**Test 4: LM Studio Plugin Compatibility**
```bash
# Start LM Studio with plugin loaded (if already installed)
# No errors in console or UI
lms --quiet &

# Check that MemPalace tools appear when agent queries tool registry via API
curl http://127.0.0.1:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "<any model>",
    "messages": [{"role": "user", "content": "list available tools"}]
  }'
# Response should include mempalace_* tools when agent is running
```

---

## Phase 1 Rollout Steps (No Wiring!)

```bash
# Step 1: Copy mempalace.py plugin to agent/plugins/ directory
copy openspec\changes\mempalace-integration\mempalace.py agent\plugins\mempalace.py

# Step 2: Install MemPalace dependencies (if not already installed)
pip install mempalace chromadb>=0.5.0,<0.7 pyyaml>=6.0

# Step 3: Create palace data directory if not exists
mkdir C:\AI\roamin-ambient-agent-tts\mem_palace_data

# Step 4 (Optional): Add configuration to .env file (or use auto-discovery without config)
# echo ROAMIN_MEMPALACE_ENABLED=true >> .env
# echo ROAMIN_MEMPALACE_MODE=plugin >> .env
# echo ROAMIN_MEMPALACE_PATH=C:\AI\roamin-ambient-agent-tts\mem_palace_data >> .env

# Step 5: Restart Roamin agent (via launch.py if in development mode)
python launch.py

# Result: Plugin auto-discovered, tools registered automatically!
# NO WIRING IN run_wake_listener.py needed — auto-discovery handles everything.
```

**Expected Behavior After Rollout**:
- LM Studio plugin sees new MemPalace tools in tool registry
- Roamin agent can use `mempalace_search` for enhanced context
- No breaking changes to existing functionality
- Graceful degradation if MemPalace not initialized

---

## Phase 2 — Standalone Capability (Future) ⏸️ DEFERRED

### Task 2.1: Add MCP Server Logic (Deferred Until Needed)

**Estimated Effort**: ~30 minutes
**Status**: ⏸️ NOT YET IMPLEMENTED
**Trigger Event**: When Claude/Cursor integration specifically requested

**Implementation Notes**:
```python
# To be added to MempalacePlugin when Phase 2 activated:

def _start_mcp_server(self):
    """Start MCP server for standalone use (Phase 2)."""
    from mempalace.mcp_server import MemPalaceMCPClient

    port_env = os.environ.get("ROAMIN_MEMPALACE_MCP_PORT", "8561")

    # Auto-detect if port already in use
    actual_port = _get_available_port(int(port_env))

    try:
        # Start MCP server process as sidecar
        self._standalone_server = subprocess.Popen(
            [sys.executable, "-m", "mempalace.mcp_server"],
            cwd=str(Path(__file__).parent),
            stdout=open("logs/mempalace_mcp.log", "a"),  # Append to log file
            stderr=subprocess.STDOUT,
        )
        logger.info(f"Mempalace MCP server started on port {actual_port}")
    except Exception as e:
        logger.error(f"Mempalace MCP server startup failed (non-fatal): {e}")
```

---

## Verification Protocol for Phase 2 Completion

### When to Implement Phase 2:

**Trigger Events**:
- Claude Code explicitly requests MemPalace access via MCP
- Cursor.sh integration needed for memory palace queries
- User reports frustration with plugin-only approach

**Before Implementation Checklist**:
1. Confirm no blocking issues from Phase 1 (plugin tools working as expected)
2. Document current LM Studio plugin usage (if using port 8561)
3. Verify available VRAM/Memory headroom for MCP server process
4. Test Port conflict detection with LM Studio running simultaneously

**Post-Implementation Verification**:
```bash
# Check both plugins/tools active:
# 1. MemPalace plugin tools in Roamin registry
curl http://127.0.0.1:1234/api/available-tools | findstr mempalace

# 2. MCP server running on port 8561
netstat -ano -p TCP | findstr "8561"

# 3. Verify no conflicts between plugin and standalone modes
grep -i "port conflict\|mcp server error" logs/wake_listener.log
```

---

## Summary of Tasks & Timeline (Updated — No Wiring!)

| Task | Effort | Status | Wiring Required? |
|------|--------|--------|-------------------|
| **1.1 Plugin Module Creation** | ~45 min | ⏳ PENDING | ❌ NO — auto-discovery handles it! |
| **1.2 Client Module Creation** | ~30 min | ⏳ PENDING | N/A — client module, not wiring |
| **1.3 Palace Directory Creation** | ~2 min | ⏳ PENDING | N/A — directory creation only |
| **1.4 Configuration Updates** | ~5 min | ⏳ PENDING | N/A — environment config only |
| **1.5 Openspec Documentation** | ✅ COMPLETE | Done | - |
| **Verification (Phase 1)** | ~20 min | ⏳ PENDING | ❌ NO wiring needed for tests! |
| **Phase 2 Implementation** | ~30 min | ⏸️ DEFERRED | Only when needed |

**Total Phase 1 Effort**: ~1.5 hours (parallelizable, NO WIRING OVERHEAD!)

---

## Key Design Guarantee: Auto-Discovery Works Like example_ping.py

```python
# Both of these work identically via auto-discovery:
agent/plugins/
├── example_ping.py          ← Auto-discovered ✅
└── mempalace.py             ← Will be auto-discovered automatically ✅

# Plugin loader scans directory on startup → handles everything automatically!
# Zero wiring in run_wake_listener.py required.
```

**This is intentional design** — plugin outlet infrastructure was built for exactly this use case!

---

## Sign-Off Checklist (After Phase 1 Complete)

- [x] Plugin file compiles cleanly (`py_compile agent/plugins/mempalace.py`)
- [x] Flake8 passes all rules with max line length=120
- [x] Graceful degradation if MemPalace unavailable (ImportError caught, palace-not-found handled)
- [x] Configuration examples added to `.env.example`
- [x] Openspec documentation complete
- [x] Verification tests pass — `discover_plugins()` → `['example_ping', 'mempalace']`; tools → `['mempalace_status', 'mempalace_search']`
- [x] **NO manual wiring in run_wake_listener.py** — auto-discovery handles it
- [x] MASTER_CONTEXT_PACK.md updated (MemPalace Integration: ✅ COMPLETE)

---

## Critical Clarification

### Why No Wiring Is Needed (vs. My Previous Thinking):

**Original Thinking**: Wired plugin into `run_wake_listener.py` startup sequence
**Correct Approach**: Plugin auto-discovery handles everything via `agent/plugins/__init__.py`

**Reasoning**:
1. Existing plugin outlet infrastructure (`agent/plugins/__init__.py`) is designed for zero-config auto-discovery
2. It scans directory, loads plugins, calls `on_load()` automatically
3. Same mechanism that loads `example_ping.py`
4. No need to duplicate work in `run_wake_listener.py`

**When Would Wiring Be Needed? (These Are Edge Cases)**:
- Programmatic plugin arguments (custom configuration at load time)
- Deferred loading until specific lifecycle event occurs
- Metrics/diagnostics tracking for loaded plugins
- Feature flags for environment-specific activation

**For Option A (LM Studio-only)**: None of these apply → Zero wiring required!

---

## Decision Required — Please Confirm

Based on your requirements and corrected understanding:

1. **Option A (Plugin-Only) for LM Studio** ✅ (current phase)
   - Design to be Option B-compatible later
   - Zero blocking of future options
   - No wiring in run_wake_listener.py needed — auto-discovery handles everything!

2. **Implementation Path**: Proceed with Phase 1 now?
   - I'll create files and deploy to your system (NO WIRING REQUIRED!)
   - Then test with LM Studio plugin integration
   - Document completion in MASTER_CONTEXT_PACK.md

**My Recommendation**: Go with **Phase 1 implementation now** with simplified approach — no wiring overhead. Auto-discovery handles everything!

---

*Openspec Location*: `C:\AI\roamin-ambient-agent-tts\openspec\changes\mempalace-integration\`
*Forward Compatibility*: ✅ Guaranteed — Option A never blocks Option B implementation
*Auto-Discovery*: ✅ Built into plugin outlet infrastructure (no wiring needed)
