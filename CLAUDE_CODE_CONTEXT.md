# Roamin Ambient Agent — Claude Code Context Pack

# Generated: 2026-03-29

# For: claude-code sessions on C:\AI\roamin-ambient-agent-tts

---

## IDENTITY

Project: Roamin — Windows-first ambient AI agent
Developer: Asherre (solo)
Repo: C:\AI\roamin-ambient-agent-tts
GitHub: jankeydadondc-byte/roamin-ambient-agent-tts (private)
Latest commit: 4932fc9
OS: Windows 10, Admin PowerShell 5.1 ONLY (no PS7, no &&, no ??)
GPU: RTX 3090 24GB
Python: 3.12, venv at C:\AI\roamin-ambient-agent-tts\.venv

---

## WHAT ROAMIN IS

An ambient AI agent that lives in the background on Windows.

- Wake hotkey: ctrl+space
- Speaks back using a cloned voice (Shawn James via Chatterbox TTS)
- Remembers facts across sessions (SQLite + ChromaDB)
- Runs a local LLM fully on GPU (no cloud, no API keys)
- Architecture: hotkey → STT → AgentLoop → LLM → TTS

---

## STACK

| Component | Tech | Location |
|---|---|---|
| Entry point | Python | run_wake_listener.py |
| Wake listener | keyboard hotkey | agent/core/voice/wake_listener.py |
| STT | Whisper (CPU) + Silero VAD | agent/core/voice/stt.py |
| LLM backend | llama-cpp-python CUDA | agent/core/llama_backend.py |
| Model router | routes tasks to models | agent/core/model_router.py |
| Agent loop | plan + execute | agent/core/agent_loop.py |
| Memory | SQLite + ChromaDB | agent/core/memory/ |
| TTS | Chatterbox (port 4123) + pyttsx3 fallback | agent/core/voice/tts.py |
| Phrase cache | 13 WAV files pre-generated | agent/core/voice/phrase_cache/ (gitignored) |
| Screen observer | PIL screenshots | agent/core/screen_observer.py |
| Tool registry | pluggable tools | agent/core/tool_registry.py |

---

## MODELS

| Task | Model | Path |
|---|---|---|
| default/chat/fast | Qwen3 8B Q4 | ~/.ollama/models/blobs/sha256-a3de86cd... |
| vision/screen | Qwen3.5 9B | ~/.lmstudio/models/lmstudio-community/Qwen3.5-9B-GGUF/ |
| reasoning | DeepSeek-R1-8B | ~/.lmstudio/models/DeepSeek-R1-0528-Qwen3-8B-Q4_K_M.gguf |
| code | Qwen3-Coder-Next | ~/.lmstudio/models/lmstudio-community/Qwen3-Coder-Next-GGUF/ |

LLM: n_gpu_layers=-1 (full GPU offload), n_ctx=8192
Build: llama-cpp-python CUDA via VS2019 + CUDA 13.1 + Ninja (~83 t/s)
Chatterbox TTS: C:\AI\chatterbox-api (Python 3.12 venv, torch 2.6.0+cu124, port 4123)
Voice sample: C:\AI\chatterbox-api\voice-sample.mp3

---

## WINDOWS STARTUP CHAIN

Startup folder: C:\Users\Asherre Roamin\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\

| Shortcut | Target | Status |
|---|---|---|
| Roamin-Chatterbox.lnk | C:\AI\chatterbox-api\_start_silent.vbs | Active |
| Roamin-ControlAPI.lnk | C:\AI\os_agent\_start_control_api.vbs | Active (fixed XMLHTTP) |
| Roamin-WakeListener.lnk | C:\AI\roamin-ambient-agent-tts\_start_wake_listener.vbs | Active |

Single-instance guard: logs/_wake_listener.lock (PID file)
Log file: logs/wake_listener.log (stdout/stderr redirected here by pythonw)

---

## MEMORY SYSTEM

SQLite DB: agent/core/memory/roamin_memory.db (gitignored)
ChromaDB: agent/core/memory/chroma_db/ (gitignored)

Tables: conversation_history, named_facts, actions_taken, observations, user_patterns

Fact extraction: regex patterns in wake_listener._extract_and_store_fact()

- Triggers: "remember my X is Y", "my X is Y", "save/note that my X is Y"
- Writes to named_facts table

Memory injection: only injects facts whose fact_name appears in the query text
(prevents irrelevant facts like favorite_color appearing in dinner suggestions)

Known facts currently stored:

- favorite color: blue

---

## THINK TIER SYSTEM

_classify_think_level(text) in wake_listener.py:

| Tier | no_think | max_tokens | Triggers |
|---|---|---|---|
| OFF | True | 60 | Default — simple queries |
| LOW | False | 512 | "think about", "analyze", "explain why/how", "figure out", "what do you think", "what would", "what if", "help me decide", "compare", "pros and cons", "difference between", "how/why does/is/are" |
| MED | False | 2048 | "really think", "think hard/carefully/deeply", "take your time", "be thorough" |
| HIGH | False | 8192 | "max thinking/effort", "think really hard", "don't/dont fuck/mess this up", "give it everything", "full effort" |

AgentLoop._classify_task() separately routes to model capabilities:

- vision: screen/look/see/observe/what am i
- code: code/program/script/function/debug/fix
- reasoning: reason/analyze/analyse
- default: everything else (including think-tier queries — intentional)

---

## TTS PHRASE CACHE

13 pre-generated WAV files at agent/core/voice/phrase_cache/ (gitignored)
Generated at warmup via warm_phrase_cache() — skips existing files on subsequent boots

Phrases:

1. "yes? how can i help you"      ← wake acknowledgment (exaggeration=0.6, cfg_weight=0.4)
2. "Done."
3. "Sorry, I didn't catch that."
4. "Working on it."
5. "The agent loop failed to complete that task."
6. "That action needs your approval."
7. "Got it."
8. "I ran into an unexpected error, something fucked up while processing that."
9. "On it."
10. "I'm not sure about that one."
11. "Give me a second."
12. "Anything else?"
13. "I didn't find anything about that."

Chatterbox 500 errors: handled with 1 retry, then pyttsx3 fallback
Emoji stripping: applied to all novel replies before TTS (re.sub non-ASCII)

---

## TIMING PROFILE (latest measurements)

| Phase | Time |
|---|---|
| Wake phrase (cached) | ~2.7s |
| STT (VAD + Whisper CPU) | ~5-6s |
| AgentLoop | ~3-12s (varies, GPU hot = fast) |
| Reply generation | ~0.1-1.5s |
| TTS novel reply (Chatterbox CUDA) | ~12-22s |
| TTS cached reply (WAV playback) | instant |
| TOTAL novel | ~20-37s |
| TOTAL cached phrase | ~5s |

VRAM note: Qwen3 8B full offload uses ~17GB. After unload + torch.cuda.empty_cache(),
Chatterbox gets ~6GB free and synthesizes in ~12s.
Layer reduction testing (31, 28 layers) showed no net gain — total stays same.

---

## CURRENT GAPS / NEXT PRIORITIES

### Immediate (next session)

1. Tool execution — AgentLoop plans steps but nothing executes yet
   - ToolRegistry exists but has no registered tools
   - First tools: open_app, web_search, file_read, screen_capture
2. Screen awareness — ScreenObserver (A3) built but not connected to voice loop
   - "what am i looking at?" should capture screen and describe it

### Near term

3. Streaming TTS — pipe model output sentence-by-sentence to Chatterbox
   - Biggest latency win: first word plays while rest generates
   - Requires rewriting router.respond() to yield tokens
2. Double-launch fix — two pythonw instances still start on VBS fire
   - Lock file guard works for subsequent launches, not the initial race

### Architecture gaps

5. RoaminCP UI — Tauri control panel in C:\AI\os_agent\ui\roamin-control
   - Has Monaco editor, xterm terminal, diff viewer
   - Not yet connected to ambient agent
2. Control API migration — ui/control_api/ not in new repo
   - Startup shortcut still points at os_agent

---

## REPO STRUCTURE

C:\AI\roamin-ambient-agent-tts\
├── run_wake_listener.py          # Entry point, lock guard, warmup, log redirect
├── agent/
│   └── core/
│       ├── voice/
│       │   ├── wake_listener.py  # Hotkey, STT, AgentLoop, memory, TTS orchestration
│       │   ├── tts.py            # Chatterbox + pyttsx3, phrase cache, retry logic
│       │   └── stt.py            # Silero VAD + Whisper
│       ├── llama_backend.py      # LlamaCppBackend, ModelRegistry singleton
│       ├── model_router.py       # Task routing, HTTP fallback
│       ├── agent_loop.py         # Plan + execute loop
│       ├── memory/
│       │   ├── memory_store.py   # SQLite CRUD + get_all_named_facts
│       │   ├── memory_search.py  # ChromaDB semantic search
│       │   └── memory_manager.py # Unified interface
│       ├── screen_observer.py    # PIL screenshot + vision model
│       ├── tool_registry.py      # Tool plugin system (empty)
│       └── context_builder.py   # Builds context for AgentLoop
├──_start_wake_listener.vbs      # Windows startup launcher (XMLHTTP, no PS flash)
├── logs/
│   ├── wake_listener.log         # All stdout/stderr from pythonw
│   └── startup.log               # VBS startup events
└── .pre-commit-config.yaml       # isort, black, flake8, mypy — all passing

---

## OPERATING RULES (non-negotiable)

1. PS5.1 only — no &&, no ??, no ternary, no here-strings
2. Every PS block starts with: Set-Location 'C:\AI\roamin-ambient-agent-tts'
3. One atomic change at a time — backup, validate, apply, verify
4. Rust edits require cargo check from src-tauri\ (60s timeout)
5. Python edits require: py_compile + flake8 + pre-commit before commit
6. No hardcoded absolute paths in Python — use Path(__file__).parent
7. No debug print() in committed code
8. Complex PS logic goes in .bat files, not inline -Command strings
9. Sandbox files at /mnt/project/ are stale — always read live from disk

## SHELL PATTERNS THAT WORK ON THIS MACHINE

# Activate venv

.venv\Scripts\Activate.ps1

# Python compile check

.venv\Scripts\python.exe -m py_compile path\to\file.py

# Flake8

.venv\Scripts\python.exe -m flake8 path\to\file.py --max-line-length=120

# Git commit (pre-commit runs automatically)

git add file.py
git commit -m "message"
git push origin main

# nvidia-smi VRAM check

nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv,noheader

# Kill wake listener instances

Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like "*run_wake_listener*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# Restart wake listener

Remove-Item "C:\AI\roamin-ambient-agent-tts\logs\_wake_listener.lock" -Force -ErrorAction SilentlyContinue
Start-Process wscript.exe -ArgumentList '"C:\AI\roamin-ambient-agent-tts\_start_wake_listener.vbs"' -WindowStyle Hidden

---

## KNOWN ISSUES / GOTCHAS

- Whisper on CPU: FP16 warning is harmless, Whisper runs FP32 on CPU
- pyttsx3 "run loop already started": only happens when two instances run simultaneously
- Chatterbox 500 on novel replies: VRAM exhaustion after llama model loads full GPU
  Workaround: unload_all() + torch.cuda.empty_cache() + 0.5s sleep before TTS
- LM Studio plugin (roamin-python-tools): permanently installed via `lms dev -i -y`
  No startup shortcut needed. Plugin at ~/.lm-studio/plugins/roamin-python-tools/
- pre-commit black reformats files: always re-add after first commit attempt fails
- CRLF patching in PS5.1: use [System.IO.File]::ReadAllText/WriteAllText
- $env:USERPROFILE fails in PS5.1 single strings: use Join-Path or bat files

---

## REFERENCE COMMITS

| Commit | What |
|---|---|
| bffef81 | A1 memory system |
| c1b63ed | A2 model router |
| b6408cf | A3 screen observer |
| 6773684 | A4 agent loop |
| 4cb680a | A5 voice interface |
| 790f4ae | TTS phrase cache (13 phrases) |
| 0886765 | Memory recall working |
| 8a7223e | Three-tier think mode |
| 3468fb0 | Fix AgentLoop reasoning triggers |
| be81473 | GPU unload + relevant-only memory injection |
| dccd5c5 | Strip emojis from TTS replies |
| 4932fc9 | Full GPU offload (layer tests concluded) |
