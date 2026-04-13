# Roamin Ambient Agent TTS

Standalone AI voice agent for Windows — always listening, never talking unless asked.

Roamin sits in your taskbar, listens for `ctrl+space`, transcribes your voice, thinks
through problems, and responds with synthesized speech. Fully local — no Ollama, no LM
Studio required. Runs Qwen3 8B (33 billion parameters) on a single RTX GPU at 80+ tokens/second.

---

## What It Does

- **Always listening** — Hotkey `ctrl+space` triggers STT (Whisper)
- **Reasons** — Plans multi-step solutions using AgentLoop + tool registry
- **Executes** — Runs web search, file I/O, plugin tools, vision, code execution
- **Remembers** — Persistent SQLite memory + ChromaDB semantic search + MemPalace
- **Speaks** — Responds via TTS with voice cloning (female/male voice synthesis)
- **Tracks tasks** — Every execution logged to Control Panel with full step details

Example voice flows:
```
You: "ctrl+space" → "What's the weather like and what should I wear?"
Roamin: "Let me check weather and give you outfit advice..."
         → web_search("current weather")
         → vision(screenshot) to see what's in your closet
         → TTS response: "It's 52°F with rain. I'd suggest..."

You: "ctrl+space" → "Find my notes from last Tuesday about the project"
Roamin: mempalace_search("project notes tuesday") → "Found: [quotes relevant memories]..."
```

---

## System Requirements

| Component | Requirement |
|-----------|-------------|
| **OS** | Windows 10 or 11 |
| **Python** | 3.12.x |
| **GPU** | NVIDIA RTX (3090, 4080, 4090, etc.) with ≥12 GB VRAM |
| **CUDA** | 12.x (for GPU acceleration) |
| **Build tools** | Visual Studio 2019+ C++ build tools |
| **RAM** | 16 GB minimum, 32 GB recommended |
| **Disk** | 20 GB free (models, venv, logs) |

**Single-GPU tested:** RTX 3090 (24 GB VRAM) runs Qwen3 8B at full speed.

---

## Quick Start

### 1. Install Prerequisites

- **Python 3.12** → https://python.org
- **CUDA Toolkit 12.x** → https://developer.nvidia.com/cuda-downloads
- **Visual Studio Build Tools** (C++ workload) → https://visualstudio.microsoft.com/downloads/

Full setup guide → [`docs/SETUP.md`](docs/SETUP.md)

### 2. Clone & Install

```powershell
cd C:\AI
git clone https://github.com/jankeydadondc-byte/roamin-ambient-agent-tts.git
cd roamin-ambient-agent-tts

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python scripts/install_llama_cpp_cuda.ps1   # Compile for GPU
```

### 3. Start Roamin

```powershell
python launch.py
# Opens Control API, wake listener, and Control Panel UI
```

Then press `ctrl+space` and speak. Roamin transcribes → thinks → responds.

---

## Using Roamin

### Voice Commands

Press `ctrl+space` and say one of these:

| Command | What Happens |
|---------|-------------|
| "What time is it?" | Direct dispatch → clock tool |
| "Search for X" | Direct dispatch → web_search |
| "Search my memories for X" | Direct dispatch → mempalace_search |
| Anything else | Full AgentLoop → planner picks tools, executes multi-step |

All interactions logged to Control Panel **Tasks** tab with step-by-step execution details.

### Control Panel

Open browser to `http://localhost:5173` (Vite dev server running in parallel):

- **Models** — Select active LLM (Qwen3, Ministral, or any gguf in model_config.json)
- **Plugins** — Install/enable/disable plugins
- **Tasks** — View execution history (goal, steps taken, outcome, duration)
- **Logs** — Live WebSocket event stream (planning, execution, errors)
- **Help** — Quick reference (voice phrases, keyboard shortcuts, links to docs)

### Configuration

Copy `.env.example` → `.env` and edit as needed:

```bash
# Optional: Protect Control API endpoints
ROAMIN_CONTROL_API_KEY=your-secret-key

# MemPalace mode: plugin (tools in Roamin), standalone (MCP server), or auto (both)
ROAMIN_MEMPALACE_MODE=plugin

# Model selection
model_config.json   # Specify which gguf files and their properties
```

See `.env.example` for all options.

---

## Project Layout

```
roamin-ambient-agent-tts/
├── agent/
│   ├── core/                    # Core engine (AgentLoop, memory, logging, context)
│   ├── plugins/                 # Auto-discovered plugins (add yours here)
│   ├── integrations/            # LM Studio API client, external services
│   └── control_api.py           # FastAPI server (models, plugins, task history, WebSocket)
│
├── ui/control-panel/            # React + Vite SPA (localhost:5173)
│   ├── src/components/          # Models, Plugins, Tasks, Logs, Help tabs
│   └── src/apiClient.js         # WebSocket + REST client
│
├── docs/                        # User and developer documentation
│   ├── SETUP.md                 # First-time environment setup
│   ├── PLUGIN_DEVELOPMENT.md    # Write your own plugins
│   ├── TROUBLESHOOTING.md       # Fix common issues
│   └── control_panel_design.md  # Architecture notes
│
├── tests/                       # Unit tests (pytest) + E2E smoke test
│   ├── unit/                    # Fast unit tests (no server needed)
│   └── test_e2e_smoke.py        # Integration test (requires Control API)
│
├── scripts/                     # Utilities
│   └── install_llama_cpp_cuda.ps1   # Build llama-cpp-python for GPU
│
├── run_wake_listener.py         # Main entry point (Roamin startup)
├── run_control_api.py           # Control API startup
├── launch.py                    # Unified launcher (starts everything)
│
└── requirements.txt             # Python dependencies
```

---

## Extending Roamin

### Write a Plugin

Plugins are `.py` files in `agent/plugins/` that register tools (functions) the agent can call.

**Minimal plugin example:**
```python
# agent/plugins/my_plugin.py
class Plugin:
    name = "my_plugin"

    def on_load(self, registry) -> None:
        registry.register(
            name="my_tool",
            description="Does something",
            risk="low",
            params={"input": "str"},
            implementation=self._run,
        )

    def _run(self, params: dict) -> dict:
        return {"result": f"Processed: {params['input']}"}
```

No wiring required — plugin auto-discovered on startup.

Full guide → [`docs/PLUGIN_DEVELOPMENT.md`](docs/PLUGIN_DEVELOPMENT.md)

### Add a Model

1. Download a `.gguf` quantized model from HuggingFace
2. Add to `model_config.json`:
```json
{
  "models": [
    {
      "id": "my_model",
      "name": "My Model",
      "path": "C:\\models\\model.gguf",
      "context_length": 8192
    }
  ]
}
```

Roamin detects it and makes it available in Control Panel.

---

## Troubleshooting

### Agent won't start

Check `roamin.log` (tail in real-time with `Get-Content roamin.log -Wait`).

Common issues and fixes → [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)

### Tests failing after changes

```powershell
# Run unit tests only (no servers needed)
.venv\Scripts\python -m pytest tests/unit/ -q
# Expected: 53 passed
```

### Wake word not triggering

- `ctrl+space` intercepted by another app → disable in Windows Settings
- Audio device wrong → set `ROAMIN_AUDIO_DEVICE` env var (see Troubleshooting guide)

---

## Architecture & Deep Dives

For architectural overview, component descriptions, and design decisions:

→ [`MASTER_CONTEXT_PACK.md`](MASTER_CONTEXT_PACK.md) (verbose, developer-facing)

For API specs and client examples:

→ `openspec/` (OpenAPI 3.0 spec, Python/JS example clients)

---

## Development

### Running Tests

```powershell
# Unit tests (fast, no servers)
pytest tests/unit/ -q

# E2E smoke test (requires Control API running)
pytest tests/test_e2e_smoke.py -q

# Specific test
pytest tests/unit/test_control_api.py::test_status -v
```

### Code Quality

```powershell
# Format
black agent/ ui/ tests/

# Lint
flake8 agent/ --max-line-length=120

# Type check (optional)
mypy agent/ --ignore-missing-imports
```

---

## Key Technologies

| Layer | Technology | Why |
|-------|-----------|-----|
| **LLM Inference** | llama-cpp-python + CUDA | Local GPU acceleration, no API calls |
| **STT** | Whisper (OpenAI) | Robust speech-to-text, offline capable |
| **TTS** | Chatterbox (custom) | Voice cloning, natural prosody |
| **Memory** | SQLite + ChromaDB + MemPalace | Persistent, semantic, searchable memories |
| **Task Execution** | AgentLoop + registry pattern | Pluggable tools, HITL approval gates |
| **UI** | React 18 + Vite + WebSocket | Real-time task monitoring, local dev server |
| **API** | FastAPI + Uvicorn | Modern async Python web framework |

---

## Status

- ✅ Voice pipeline (STT → TTS via Whisper + Chatterbox)
- ✅ Reasoning engine (AgentLoop with tool dispatch)
- ✅ Plugin system (auto-discovered, zero wiring)
- ✅ Memory (SQLite task history + ChromaDB semantic search + MemPalace)
- ✅ Control Panel UI (real-time task monitoring, plugin management)
- ✅ Security (API key auth, audit logging, approval gates)
- ✅ Testing (53 unit tests, E2E smoke tests, 100% core module coverage)
- ✅ Documentation (setup, plugins, troubleshooting, architecture)

---

## License

MIT (private repo)

---

## Questions?

1. **First-time setup?** → [`docs/SETUP.md`](docs/SETUP.md)
2. **Writing a plugin?** → [`docs/PLUGIN_DEVELOPMENT.md`](docs/PLUGIN_DEVELOPMENT.md)
3. **Something broken?** → [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)
4. **Deep architecture?** → [`MASTER_CONTEXT_PACK.md`](MASTER_CONTEXT_PACK.md)

---

**Roamin is ready to listen. Press `ctrl+space` and speak.**
