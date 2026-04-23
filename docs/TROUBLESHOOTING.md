# Troubleshooting Guide

This guide covers every issue encountered during development of Priorities 1–9.
If you hit a problem, find your symptom below.

---

## Agent Won't Start

### `keyboard` Import Error

**Symptom:** Error on startup: `keyboard` module not found or permission denied

**Cause:** The `keyboard` library (for `ctrl+space` hotkey detection) requires elevated
permissions on Windows. It cannot run in a standard user context.

**Fix:**
1. Open Command Prompt as Administrator
2. Navigate to project: `cd C:\AI\roamin-ambient-agent-tts`
3. Activate venv: `.\.venv\Scripts\Activate.ps1`
4. Run: `python run_wake_listener.py`

Alternatively, double-click `_start_wake_listener.vbs` — it auto-elevates.

### `llama-cpp-python` Crash on Import

**Symptom:** `ImportError: DLL load failed` or `No module named '_ctypes_test'` at startup

**Cause:** `llama-cpp-python` was not built with CUDA support, or CUDA libraries are
not in PATH.

**Fix:**
```powershell
# Rebuild llama-cpp-python with CUDA
.venv\Scripts\python scripts/install_llama_cpp_cuda.ps1
```

Verify CUDA is installed: `nvcc --version` should print version info.

### Port 8765 Already in Use

**Symptom:** `Address already in use` when starting Control API

**Cause:** Another Control API process is already running (from a previous launch or
stale terminal).

**Fix:**
```powershell
# Find the PID using port 8765
netstat -ano | findstr "8765"
# Output: TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       1234

# Kill it by PID
taskkill /PID 1234 /F

# Or find and kill all python.exe processes (CAREFUL)
taskkill /IM python.exe /F  # ← kills ALL python — only if stuck
```

---

## Wake Word Doesn't Trigger

### `ctrl+space` Hotkey Intercepted by Another App

**Symptom:** Press `ctrl+space` but Roamin doesn't say "Yes?" — nothing happens

**Cause:** Another application (Discord, VS Code, Windows settings) has bound the same
hotkey globally.

**Fix:**
1. Windows Settings → Device → Keyboard → Advanced keyboard settings
2. Scroll to bottom, click "Open the Settings app" under "Explore input personalization options"
3. Look for `ctrl+space` bindings and disable them
4. Restart Roamin

Or try a different wake phrase by editing `run_wake_listener.py` line ~XX (search for
`"ctrl+space"`).

### Wrong Audio Device Selected

**Symptom:** Roamin doesn't hear you; STT input is silent or picks up system audio only

**Cause:** `sounddevice` is using the wrong microphone. Many systems have multiple audio
devices.

**Fix:**
```powershell
# List all audio devices
python -c "import sounddevice; print(sounddevice.query_devices())"
# Output shows device index, name, channels

# Find your microphone's index number (e.g., 2), then set env var:
$env:ROAMIN_AUDIO_DEVICE = 2
python run_wake_listener.py
```

Or add to `.env`:
```
ROAMIN_AUDIO_DEVICE=2
```

---

## Control Panel Shows "Disconnected"

### Control API Not Running

**Symptom:** Control Panel UI loads but shows "disconnected" in top-right, WebSocket status red

**Cause:** Control API server is not running on port 8765.

**Fix:**
```powershell
# Start Control API in a separate terminal
python run_control_api.py
# Should print: "Uvicorn running on http://127.0.0.1:8765"

# Or use the unified launcher (recommended)
python launch.py
```

### Port Mismatch

**Symptom:** "Disconnected" persists even though Control API is running locally

**Cause:** Control Panel is looking for Control API at the wrong address.

**Fix:** Check `ui/control-panel/index.html` line ~10:
```html
<script>
  window.__CONTROL_API_URL__ = 'http://127.0.0.1:8765';
</script>
```

If the port is different (e.g., your Control API runs on 9000), update it:
```html
<script>
  window.__CONTROL_API_URL__ = 'http://127.0.0.1:9000';
</script>
```

Then reload the page.

### Control Panel Dev Server Not Running

**Symptom:** Cannot reach Control Panel at `http://localhost:5173`

**Cause:** Vite dev server is not running.

**Fix:**
```powershell
cd ui/control-panel
npm run dev
# Should print: "Local: http://localhost:5173"
```

---

## Task History Shows No Tasks

### SQLite Database Not Created Yet

**Symptom:** Control Panel → Tasks tab is empty, even after running commands

**Cause:** The `task_runs` and `task_steps` SQLite tables are created on first use.
If no tasks have been run yet, the database is empty.

**Fix:**
1. Ask Roamin to do something via voice: `ctrl+space` → "what time is it?"
2. One task should be logged to `task_runs`
3. Return to Control Panel → Tasks → refresh (or wait for WebSocket push)

### Wrong SQLite Database Path

**Symptom:** Tasks appear in one terminal but not in Control Panel

**Cause:** `memory_store.py` is using a different database path than expected.
Default is `./roamin.db` (project root).

**Fix:**
```powershell
# Verify database exists
ls *.db
# Should show: roamin.db (if empty, run a task first)

# Check database size (should be >0 bytes after running tasks)
(Get-Item roamin.db).Length
```

If you set `ROAMIN_DB_PATH` env var, verify it matches what Control Panel expects.

---

## LM Studio Model Not Appearing in Control Panel

### `model_config.json` Not Found or Invalid

**Symptom:** Control Panel → Models dropdown is empty, or shows "error loading models"

**Cause:** `model_config.json` doesn't exist at project root, or has syntax errors.

**Fix:**
1. Create `model_config.json` at project root:
```json
{
  "models": [
    {
      "id": "ministral-8b",
      "name": "Ministral 8B",
      "path": "C:\\path\\to\\ministral-8b.gguf",
      "context_length": 8192
    }
  ]
}
```

2. Verify JSON is valid: `python -c "import json; json.load(open('model_config.json'))"`

3. Restart Control API: kill the `python run_control_api.py` process and start it again

### LM Studio Not Running

**Symptom:** Control Panel shows LM Studio models but they never load, or Control API
falls back to llama-cpp-python

**Cause:** LM Studio is not running on its expected port (default: 1234).

**Fix:**
1. Start LM Studio — it should print port in console
2. In Control Panel, check if LM Studio models appear in the dropdown
3. If they don't, check `roamin.log`:
```powershell
tail -f roamin.log | findstr "lm studio"
```

Note: If LM Studio isn't running, Roamin will fall back to llama-cpp-python (Qwen3).
This is expected behaviour.

---

## MemPalace Search Returns Nothing

### Palace Not Mined / Indexed

**Symptom:** Roaming asks "search my memories for X" → tool returns "No memories found"

**Cause:** The palace exists but has no data. You must run `mempalace mine` to index
project files.

**Fix:**
```powershell
# Index all project files into the palace
mempalace mine .
# Should print: "1590 drawers filed across 172 files"

# Verify palace initialized
mempalace status --palace mem_palace_data
# Should show: wings, rooms, drawers count
```

### Wrong Palace Path

**Symptom:** `mempalace_status` tool returns error: "Palace not initialized"

**Cause:** `ROAMIN_MEMPALACE_PATH` env var points to wrong directory.

**Fix:**
1. Check env var: `$env:ROAMIN_MEMPALACE_PATH` (in PowerShell)
2. Default is: `C:\AI\roamin-ambient-agent-tts\mem_palace_data`
3. If not set, update `.env`:
```
ROAMIN_MEMPALACE_PATH=C:\AI\roamin-ambient-agent-tts\mem_palace_data
```
4. Restart agent

### MemPalace Package Not Installed

**Symptom:** Tool error: "mempalace package not installed"

**Cause:** `mempalace` not in active venv.

**Fix:**
```powershell
.venv\Scripts\pip install mempalace
```

---

## Tests Failing After Code Changes

### Run Unit Tests Only (No Server Needed)

**Symptom:** Want to verify you didn't break anything, but don't want to start servers

**Fix:**
```powershell
# Fast: run only unit tests (no server startup)
.venv\Scripts\python -m pytest tests/unit/ -q
# Expected: "53 passed"

# With verbose output (see each test name)
.venv\Scripts\python -m pytest tests/unit/ -v

# Run one specific test
.venv\Scripts\python -m pytest tests/unit/test_control_api.py::test_status -v
```

### Test Import Errors

**Symptom:** `ModuleNotFoundError: No module named 'agent'` when running tests

**Cause:** Tests are being run outside the project directory or venv is not active.

**Fix:**
```powershell
# Verify you're in the right directory
pwd  # should end with roamin-ambient-agent-tts

# Verify venv is active
.venv\Scripts\python -c "import sys; print(sys.prefix)"  # should be your .venv path

# Then run tests
.venv\Scripts\python -m pytest tests/unit/ -q
```

### Test Timeout or Hang

**Symptom:** `pytest` runs a test but hangs forever; `ctrl+C` needed to stop

**Cause:** Async test not using `pytest-asyncio` fixture, or mock is missing.

**Fix:** Check the test file — it should have:
```python
import pytest

@pytest.mark.asyncio
async def test_something():
    result = await some_async_function()
    assert result == expected
```

If the test doesn't use `@pytest.mark.asyncio`, add it.

---

## Checking Logs

### Where Are the Logs?

| Log File | Location | Contains |
|---|---|---|
| **Agent main log** | `roamin.log` | All INFO+ from wake_listener.py and AgentLoop (startup, commands, errors) |
| **Control API** | printed to terminal | FastAPI startup, request errors, WebSocket connections |
| **MemPalace MCP** | `logs/mempalace_mcp.log` | MCP server output (only when `ROAMIN_MEMPALACE_MODE=auto` or `standalone`) |
| **Audit log** | `logs/audit.log` | HIGH-risk tool executions (with timestamp, tool name, result) |
| **Python error** | `roamin.log` | Exceptions, tracebacks |

### Read the Main Log in Real-Time

```powershell
# Windows PowerShell: tail the log as it updates
Get-Content roamin.log -Wait -Tail 20

# Or: print last 50 lines
Get-Content roamin.log -Tail 50
```

### Search Logs for Specific Error

```powershell
# Find all ERROR-level lines
Select-String "ERROR" roamin.log

# Find lines mentioning a specific tool
Select-String "mempalace" roamin.log

# Count how many times a phrase appears
(Select-String "warning" roamin.log).Count
```

### Clear Logs (Start Fresh)

```powershell
# Delete log files (careful — can't undo)
Remove-Item roamin.log
Remove-Item logs/audit.log
Remove-Item logs/mempalace_mcp.log

# Next run will create fresh logs
python run_wake_listener.py
```

---

## Still Stuck?

1. **Check `roamin.log`** — 99% of issues print a traceback there
2. **Run tests** — `pytest tests/unit/ -q` to rule out environment issues
3. **Check `MASTER_CONTEXT_PACK.md`** — architectural overview if you need to understand how components fit together
4. **Read relevant source** — if a tool is behaving oddly, the docstring in its `.py` file often explains it

If none of these help, the issue is likely novel — add it to this guide when you solve it.
