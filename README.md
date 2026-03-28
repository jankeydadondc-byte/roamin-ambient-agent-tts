# Roamin Ambient Agent TTS

Standalone ambient AI agent for Windows. Fully self-contained — no Ollama or LM Studio required at runtime.

## What it does
- Listens for `ctrl+space` wake word
- Transcribes speech via Whisper STT
- Plans and executes tasks via AgentLoop
- Responds via Chatterbox TTS with voice cloning
- Runs Qwen3 8B directly on GPU via llama-cpp-python (83 t/s on RTX 3090)
- Persistent memory via SQLite + ChromaDB

## Requirements
- Windows 10/11
- Python 3.12
- RTX GPU (tested on RTX 3090)
- CUDA 13.1
- VS 2019 Build Tools (for llama-cpp-python CUDA build)

## Setup
```powershell
cd C:\AI\roamin-ambient-agent-tts
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Install llama-cpp-python with CUDA (see docs/llama_cpp_install.md)
```

## Startup
Double-click `_start_control_api.vbs` then `_start_wake_listener.vbs`
Or add both to Windows Startup folder for auto-start on login.

## Wake word
`ctrl+space` — Roamin says "Yes?", listens for 5 seconds, executes your command.
