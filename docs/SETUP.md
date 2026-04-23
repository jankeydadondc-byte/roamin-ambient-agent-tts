# Setup Guide

Complete step-by-step instructions to get Roamin running from a fresh Windows machine.

---

## Prerequisites

### 1. Python 3.12

**Download:** https://www.python.org/downloads/

1. Click "Download Python 3.12.x"
2. Run the installer
3. **Important:** Check "Add Python to PATH"
4. Click Install

**Verify:**
```powershell
python --version
# Should print: Python 3.12.x
```

### 2. Node.js 18+ (Optional, for Control Panel Development)

**Download:** https://nodejs.org/

If you only run Roamin without modifying the Control Panel UI, you can skip this.

1. Download LTS version
2. Run installer, keep defaults
3. Verify:
```powershell
node --version
npm --version
```

### 3. CUDA Toolkit 12.x

**Why:** llama-cpp-python needs CUDA to run Qwen3 8B fast on GPU.

**Download:** https://developer.nvidia.com/cuda-downloads

1. Select OS: Windows, Architecture: x86_64, Version: 12.x (any recent 12.x)
2. Download installer (2–3 GB)
3. Run installer, keep defaults (installs to `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x`)
4. Verify:
```powershell
nvcc --version
# Should print: release 12.x
```

If `nvcc` command not found, add to PATH:
- Windows Settings → Environment Variables → edit `Path` → add `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin`
- Restart PowerShell

### 4. Visual Studio Build Tools

**Why:** Compiling llama-cpp-python requires a C++ compiler.

**Download:** https://visualstudio.microsoft.com/downloads/ → "Visual Studio Build Tools"

1. Run installer
2. Click "Desktop development with C++" workload
3. Click Install (takes ~5 min)

---

## Clone the Repository

```powershell
cd C:\AI
git clone https://github.com/jankeydadondc-byte/roamin-ambient-agent-tts.git
cd roamin-ambient-agent-tts
```

If `git` is not installed, download from https://git-scm.com/.

---

## Python Virtual Environment

```powershell
# Create venv in project directory
python -m venv .venv

# Activate venv
.\.venv\Scripts\Activate.ps1

# Verify venv is active (prompt should show "(.venv)" prefix)
```

**If activation fails with permissions error:**
```powershell
# Allow script execution in this session only
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate.ps1
```

---

## Install Python Dependencies

With venv active:

```powershell
# Upgrade pip (ensures smooth installs)
python -m pip install --upgrade pip

# Install all dependencies from requirements.txt
pip install -r requirements.txt
# This takes ~2 minutes on first install
```

**What just installed:**
- `chromadb` — semantic search backend for MemPalace
- `mempalace` — semantic memory system
- `pyttsx3` + `openai-whisper` — voice I/O
- `torch` — deep learning framework for models
- `fastapi` + `uvicorn` — Control API web server
- `pytest` — testing framework
- And ~30 more supporting libraries

---

## Install llama-cpp-python with CUDA

This is the most complex step. The package needs to be compiled for your GPU.

```powershell
# Run the install script (handles all the flags)
.venv\Scripts\python scripts/install_llama_cpp_cuda.ps1

# Expected output (partial):
# CMake detected CUDA at C:\Program Files\NVIDIA...
# Building wheels for collected packages: llama-cpp-python
# Successfully built llama_cpp_python
```

If that script doesn't exist or fails, manual install:

```powershell
# Set environment variables for the build
$env:CMAKE_ARGS = "-DLLAMA_CUDA=on"
$env:FORCE_CMAKE = "on"

# Install
pip install llama-cpp-python

# Verify it compiled with CUDA
python -c "from llama_cpp import Llama; print('CUDA support loaded')"
```

---

## Initialize MemPalace (Semantic Memory)

MemPalace indexes project files into semantic memory for context-aware queries.

```powershell
# Create the palace data directory
mkdir mem_palace_data

# Index all project files (runs once)
mempalace mine .

# Expected output:
# 1590 drawers filed across 172 files

# Verify palace is initialized
mempalace status --palace mem_palace_data
# Should print: wings, rooms, drawers count
```

If `mempalace` command not found, it was installed but not in PATH:
```powershell
.venv\Scripts\python -m mempalace mine .
```

---

## Configure Environment

```powershell
# Copy template to live config
Copy-Item .env.example -Destination .env

# Edit .env if needed (most defaults work)
notepad .env
```

### Key Environment Variables

| Variable | Default | Example | Notes |
|---|---|---|---|
| `ROAMIN_CONTROL_API_KEY` | (not set) | `your-secret-key` | Optional. Protects Control API endpoints. |
| `LM_API_TOKEN` | (not set) | `sk-lm-...` | Only needed if using LM Studio. |
| `ROAMIN_MEMPALACE_MODE` | `plugin` | `plugin` / `auto` | `plugin` = tools in Roamin; `auto` = also start MCP server. |
| `ROAMIN_MEMPALACE_PATH` | `mem_palace_data/` | `./mem_palace_data` | Where semantic memory lives. |
| `ROAMIN_AUDIO_DEVICE` | (auto-detect) | `2` | Device index if auto-detect picks wrong mic. |

---

## Set Up Model Configuration

Roamin can use multiple LLMs. Specify them in `model_config.json` at project root.

```json
{
  "models": [
    {
      "id": "qwen3-8b",
      "name": "Qwen3 8B",
      "path": "C:\\models\\qwen3-8b-instruct-q4_k_m-00001-of-00003.gguf",
      "context_length": 32768,
      "task_type": "reasoning"
    },
    {
      "id": "ministral-8b",
      "name": "Ministral 8B",
      "path": "C:\\models\\Ministral-8B-Instruct-2410.Q4_K_M.gguf",
      "context_length": 32768,
      "task_type": "reasoning"
    }
  ]
}
```

**Fields:**
- `id` — unique identifier (used in Control Panel)
- `name` — display name
- `path` — absolute path to the `.gguf` file
- `context_length` — max tokens model accepts
- `task_type` — `reasoning`, `vision`, `tts` (for routing)

**Where to get models:**
- https://huggingface.co/models?library=gguf (search "gguf", filter by model size)
- Download `.gguf` files to a models directory (e.g., `C:\models\`)

---

## Verify Installation

Run these checks before starting:

```powershell
# 1. Python environment
python --version
# Python 3.12.x

# 2. venv is active
where python
# Should show: C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python

# 3. Key libraries load
python -c "from agent.core.memory import MemoryManager; print('✓ Memory')"
python -c "from mempalace.searcher import search_memories; print('✓ MemPalace')"
python -c "from llama_cpp import Llama; print('✓ llama-cpp-python')"

# 4. Control API starts (should print "Uvicorn running...")
python run_control_api.py
# Press Ctrl+C to stop

# 5. Database exists
ls *.db
# Should be empty until first task is run
```

All checks should pass before moving on.

---

## First Run

### Option A: Using the Unified Launcher (Recommended)

```powershell
python launch.py
# Opens:
# - Control API on http://127.0.0.1:8765
# - Wake listener (listens for ctrl+space)
# - Vite dev server on http://localhost:5173 (Control Panel UI)
```

### Option B: Manual (Separate Terminals)

**Terminal 1 — Control API:**
```powershell
.\.venv\Scripts\Activate.ps1
python run_control_api.py
# Prints: "Uvicorn running on http://127.0.0.1:8765"
```

**Terminal 2 — Wake Listener:**
```powershell
.\.venv\Scripts\Activate.ps1
python run_wake_listener.py
# Waits for ctrl+space
```

**Terminal 3 — Control Panel (optional):**
```powershell
cd ui\control-panel
npm install  # First time only
npm run dev
# Prints: "Local: http://localhost:5173"
```

---

## Using Roamin

### Voice Control

1. Press `ctrl+space` (or your configured hotkey)
2. Roamin says "Yes?" (via TTS)
3. Speak your command (5-second window)
4. Roamin transcribes → plans → executes
5. Results shown in Control Panel, roamin.log, and via TTS

### Control Panel

Open browser to `http://localhost:5173` (if running Vite dev server):

- **Models** — select which LLM to use for next task
- **Plugins** — list installed plugins, enable/disable
- **Tasks** — view execution history, see what the agent did
- **Logs** — live WebSocket events (planning, execution, errors)
- **Help** — quick reference for commands and keyboard shortcuts

---

## Troubleshooting Setup

### `python: command not found`

Python not in PATH. Add it:
1. Windows Settings → Environment Variables
2. Edit `Path` variable
3. Add `C:\Users\<your-username>\AppData\Local\Programs\Python\Python312`
4. Restart PowerShell

### `pip install` fails with permission error

Run PowerShell as Administrator:
- Right-click PowerShell → "Run as administrator"
- Then run `pip install -r requirements.txt`

### CUDA not detected by llama-cpp-python

Check NVIDIA GPU is present:
```powershell
nvidia-smi
# Should show GPU name and memory
```

If not present, install CUDA first (see Prerequisites). If present but build still fails,
try manual install with verbose output:
```powershell
$env:CMAKE_ARGS = "-DLLAMA_CUDA=on"
pip install -v llama-cpp-python 2>&1 | Tee-Object cmake_build.log
```

Check `cmake_build.log` for error messages.

### Model files not loading

Verify paths in `model_config.json` are absolute and files exist:
```powershell
ls "C:\models\qwen3-8b.gguf"
# File not found means path is wrong or file wasn't downloaded
```

### MemPalace "palace not initialized"

Rerun mining:
```powershell
mempalace mine .
```

Or if that fails, reinitialize:
```powershell
rm -r mem_palace_data
mkdir mem_palace_data
mempalace mine .
```

---

## Next Steps

1. **Try a voice command** → `ctrl+space` → "what time is it?"
2. **Check Control Panel** → http://localhost:5173 → Tasks tab should show your task
3. **Read the plugin guide** → `docs/PLUGIN_DEVELOPMENT.md` (extend functionality)
4. **Check the troubleshooting guide** → `docs/TROUBLESHOOTING.md` (if anything breaks)

For detailed architecture, see `MASTER_CONTEXT_PACK.md`.
