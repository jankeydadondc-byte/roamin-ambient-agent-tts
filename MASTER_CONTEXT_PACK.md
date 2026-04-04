# Roamin Ambient Agent — Master Context Pack

# Updated: 2026-04-03 (standalone filesystem model discovery complete — no external servers required)

# For: new Claude conversations to pick up where we left off

# Repo: C:\AI\roamin-ambient-agent-tts

# GitHub: jankeydadondc-byte/roamin-ambient-agent-tts (private)

# Latest commit: 90eec34 (code); model_sync fully rewritten this session

---

## IDENTITY & HARDWARE

Project: Roamin — Windows-first always-on ambient AI agent (no cloud, no API keys)
Developer: Asherre (solo, neurodivergent, building this for personal use)
Primary shell: Admin PowerShell 5.1 ONLY
GPU: RTX 3090 24GB VRAM
Python: 3.12
Venv: C:\AI\roamin-ambient-agent-tts\.venv
OS: Windows 10

---

## WHAT ROAMIN IS

Roamin is an ambient AI assistant that runs silently in the background on Windows.

- Press ctrl+space → it wakes, listens, thinks, and responds in a cloned voice
- Fully local — no internet required (except for web_search tool)
- Remembers facts across sessions via SQLite + ChromaDB
- Can execute tools: web search, clipboard, processes, memory recall, screenshots + vision
- Architecture: ctrl+space → STT → direct dispatch OR AgentLoop → LLM → TTS

---

## REPO STRUCTURE

C:\AI\roamin-ambient-agent-tts\
├── run_wake_listener.py           # Entry point, RUST_LOG=warn, lock guard, warmup, log pruning, TeeStream stdout/stderr tee to console+log
├──_start_wake_listener.vbs       # Windows startup launcher (lock file + WMI dual guard)
├── _launch_and_monitor.ps1        # Kill dupes, clear log, launch, tail filtered log
├── CONSOLIDATED_PRIORITIES.md     # Unified roadmap (Priorities 1-7, phase-based)
├── MASTER_CONTEXT_PACK.md         # This file — full context for new sessions
├── models/
│   ├── Qwen3-VL-8B-Instruct-abliterated-v2.Q4_K_M.gguf  (4.68GB — default model)
│   └── Qwen3-VL-8B-Instruct-abliterated-v2.mmproj-Q8_0.gguf  (718MB — vision encoder)
├── agent/
│   └── core/
│       ├── voice/
│       │   ├── wake_listener.py   # Main orchestration: hotkey→STT→dispatch→LLM→TTS
│       │   ├── tts.py             # Chatterbox + pyttsx3 fallback, phrase cache
│       │   └── stt.py             # Silero VAD + Whisper CUDA (enabled commit a47b2f2, ~0.5s)
│       ├── llama_backend.py       # LlamaCppBackend, ModelRegistry singleton, ALL models
│       ├── model_router.py        # Task→model routing; file_path dispatch → LlamaCppBackend, then HTTP fallback
│       ├── model_sync.py          # Filesystem GGUF discovery (LM Studio dirs + drive walk + Ollama blobs); runs at startup
│       ├── model_config.json      # Routing rules, fallback chain, model endpoints; model_scan_dirs key; file_path on llama_cpp entries
│       ├── agent_loop.py          # Plan + execute loop (cancellation, per-step timeouts)
│       ├── tools.py               # 28 tool implementations (input validation, structured errors)
│       ├── tool_registry.py       # Tool plugin system wired to tools.py
│       ├── memory/
│       │   ├── memory_store.py    # SQLite CRUD + get_all_named_facts
│       │   ├── memory_search.py   # ChromaDB semantic search
│       │   └── memory_manager.py  # Unified interface
│       ├── screen_observer.py     # PIL screenshot + HTTP vision API (HTTP path disabled — uses fast-path)
│       └── context_builder.py     # Builds text context for AgentLoop
├── logs/
│   ├── wake_listener.log          # All stdout/stderr (auto-pruned 40KB max / 15KB tail)
│   └── startup.log                # VBS startup events
└── .gitignore                     # Includes .claude/, workspace/, phrase_cache/, *.db

---

## FULL MODEL REGISTRY (llama_backend.py CAPABILITY_MAP + model_config.json auto-discovery)

| Capability key(s) | Model | File size | VRAM | Notes |
|---|---|---|---|---|
| **default, chat, fast, vision, screen_reading** | **Qwen3-VL-8B Abliterated v2 Q4_K_M + mmproj** | **4.7GB + 718MB** | **~5.4GB** | **DEFAULT: unified chat+vision, uncensored. VISION WORKING ✅** |
| reasoning, analysis | DeepSeek R1 8B Q4 | 4.7GB | ~5GB | Deep think tasks |
| ministral, ministral_reasoning | Ministral 3 14B Q4 | 7.7GB | ~8GB | Vision + reasoning |
| ministral_vision | Ministral 3 14B Q4 + mmproj | 7.7GB + 0.8GB | ~9GB | Ministral with screen |
| code, heavy_code | Qwen3 Coder Next 80B Q4 | 45.2GB | >24GB | CPU offload only |
| (legacy fallback) | Qwen3 8B Q4 | 4.9GB | ~14GB | Old default, HTTP fallback only |

**Auto-discovered models (added by model_sync at first run — 2026-04-03):**

| Slug | File |
|---|---|
| deepseek-r1-0528-qwen3-8b-q4-k-m | ~/.lmstudio/models/DeepSeek-R1-0528-Qwen3-8B-Q4_K_M.gguf |
| deepseek-r1-distill-qwen-14b-q4-k-m | ~/.lmstudio/models/.../DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf |
| ministral-3-14b-reasoning-2512-q4-k-m | ~/.lmstudio/models/.../Ministral-3-14B-Reasoning-2512-Q4_K_M.gguf |
| qwen2-5-coder-14b-instruct-q4-k-m | ~/.lmstudio/models/.../Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf |
| qwen3-coder-next-q4-k-m | ~/.lmstudio/models/.../Qwen3-Coder-Next-Q4_K_M.gguf |
| qwen3-5-9b-q4-k-m | ~/.lmstudio/models/.../Qwen3.5-9B-Q4_K_M.gguf |

Model paths (all GGUF, all validated at runtime):

- **Qwen3-VL-8B (DEFAULT):** C:\AI\roamin-ambient-agent-tts\models\Qwen3-VL-8B-Instruct-abliterated-v2.Q4_K_M.gguf
- **Qwen3-VL-8B mmproj:** C:\AI\roamin-ambient-agent-tts\models\Qwen3-VL-8B-Instruct-abliterated-v2.mmproj-Q8_0.gguf
- Qwen3 8B (legacy): C:\Users\Asherre Roamin\.ollama\models\blobs\sha256-a3de86cd...
- DeepSeek R1: ..\.lmstudio\models\DeepSeek-R1-0528-Qwen3-8B-Q4_K_M.gguf
- Ministral 14B: ..\.lmstudio\models\lmstudio-community\Ministral-3-14B-Reasoning-2512-GGUF\Ministral-3-14B-Reasoning-2512-Q4_K_M.gguf
- Ministral mmproj: ...same dir...\mmproj-Ministral-3-14B-Reasoning-2512-F16.gguf
- Qwen3 Coder: ..\.lmstudio\models\lmstudio-community\Qwen3-Coder-Next-GGUF\Qwen3-Coder-Next-Q4_K_M.gguf

mmproj auto-resolution: _MMPROJ_MAP dict maps model_path → mmproj_path (no hardcoded capability checks)
Vision handler: Qwen25VLChatHandler (falls back to Llava15ChatHandler for non-Qwen-VL models)
Multimodal detection: chat() checks `any(isinstance(msg["content"], list) for msg in messages)`
  → routes to create_chat_completion() which invokes the chat handler and mmproj

Prompt formats (auto-detected from model path):

- Qwen3/DeepSeek: ChatML (<|im_start|> tokens), with no_think=True injects <think>\n\n</think>
- Ministral/Mistral: [INST] ... [/INST] format

n_gpu_layers=-1 (full GPU offload)
Per-capability n_ctx (_CAPABILITY_N_CTX dict in llama_backend.py):

- default/chat/fast/vision/screen_reading → 8192 (Qwen3-VL-8B — VRAM-constrained by mmproj)
- reasoning/analysis → 32768 (DeepSeek R1 — loads exclusively, full context available)
- ministral/ministral_vision/ministral_reasoning → 32768 (Ministral 14B — loads exclusively)
- code/heavy_code → 16384 (Coder models)
llama-cpp-python built with VS2019 + CUDA 13.1 + Ninja

---

## WINDOWS STARTUP CHAIN

Startup folder: C:\Users\Asherre Roamin\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\

| Shortcut | Target | Notes |
|---|---|---|
| Roamin-Chatterbox.lnk | C:\AI\chatterbox-api\_start_silent.vbs | ✅ Active |
| Roamin-ControlAPI.lnk | C:\AI\os_agent\_start_control_api.vbs | ✅ Fixed (native XMLHTTP) |
| Roamin-WakeListener.lnk | C:\AI\roamin-ambient-agent-tts\_start_wake_listener.vbs | ✅ Active |

LM Studio plugin: permanently installed via `lms dev -i -y`
Plugin location: C:\Users\Asherre Roamin\.lm-studio\plugins\roamin-python-tools\
Auto-loads with LM Studio. No startup shortcut needed.

Chatterbox TTS:

- Location: C:\AI\chatterbox-api
- Port: 4123, DEVICE=cuda (in .env)
- Voice sample: C:\AI\chatterbox-api\voice-sample.mp3 (Shawn James clone)
- venv: Python 3.12, torch 2.6.0+cu124
- VBScript auto-launches Chatterbox if not running (checks ports 4123-4129 via MSXML2.XMLHTTP before launching Roamin)

---

## VOICE PIPELINE (wake_listener.py_on_wake flow)

1. ctrl+space fires → _on_wake_thread →_on_wake
2. Speak cached wake phrase: "yes? how can i help you" (~2.7s from cache)
3. STT: Silero VAD listens → stops on silence → Whisper transcribes (~0.5-1s CUDA)
4. Memory: _extract_and_store_fact() → regex-extract facts → write to named_facts
5. Memory: _build_memory_context() → only inject facts whose name appears in query
6. Layer 1 — Direct dispatch: _try_direct_dispatch(transcription, registry)
   - Pattern-matches against known tool intents (regex, not exact substrings)
   - Screen triggers: 10 regex patterns covering natural voice phrasings
   - If match AND success AND screenshot_path present: VISION FAST-PATH (see below)
   - If match AND success AND no screenshot_path: use tool result as text context, skip AgentLoop
   - If match AND failure: FALL THROUGH to AgentLoop (resilience pass)
   - Returns dict with {success, result, screenshot_path?} or None
7. VISION FAST-PATH (new — vision pass 2026-04-01):
   - Triggered when direct dispatch returns screenshot_path
   - PIL loads screenshot, thumbnail to 1024x1024, base64-encodes
   - Builds multimodal messages: system prompt + [text, image_url]
   - router.respond("vision", transcription, messages=vision_messages)
   - LlamaCppBackend.chat() detects list content → create_chat_completion()
   - Qwen25VLChatHandler processes image through mmproj → Qwen3-VL-8B describes screen
   - Reply spoken, function returns (skips text-model path entirely)
   - try/except fallback: if vision fails, falls through to text description path
8. Layer 2 — AgentLoop (if no direct match OR direct dispatch failed):
   - _classify_task() → vision/code/reasoning/default
   - _generate_plan() → LLM returns JSON steps
   - _execute_step() → registry.execute() per step (30s timeout per tool)
   - cancel() method + threading.Event for graceful mid-plan cancellation
9. tool_context: ASCII-stripped, max 1500 chars
10. Think tier: _classify_think_level() → (no_think, max_tokens)
11. Reply: router.respond("default", ..., messages, max_tokens, no_think)
12. Strip <think> blocks, strip non-ASCII (emojis), truncate to 200 chars
13. TTS: speak(reply) — cache hit = instant, miss = Chatterbox synthesis (~8-26s)
14. Store conversation to memory

---

## TTS PHRASE CACHE

Location: agent/core/voice/phrase_cache/ (gitignored, regenerated at warmup)
warm_phrase_cache() called at startup — skips already-cached WAV files

13 pre-generated phrases with MD5-hashed filenames:

1. "yes? how can i help you"     exaggeration=0.6, cfg_weight=0.4
2. "Done."
3. "Sorry, I didn't catch that."
4. "Working on it."
5. "The agent loop failed to complete that task."
6. "That action needs your approval."
7. "Got it."                     exaggeration=0.6, cfg_weight=0.4
8. "I ran into an unexpected error, something fucked up while processing that."
9. "On it."                      exaggeration=0.6, cfg_weight=0.4
10. "I'm not sure about that one."
11. "Give me a second."
12. "Anything else?"
13. "I didn't find anything about that."

Chatterbox 500 errors: retry once → pyttsx3 fallback
VRAM budget: Qwen3-VL-8B (~5.4GB) + Chatterbox (~3GB) = ~8.4GB — 15.6GB headroom on 24GB RTX 3090

---

## THREE-TIER THINK MODE (_classify_think_level in wake_listener.py)

| Tier | no_think | max_tokens | Triggers |
|---|---|---|---|
| OFF | True | 60 | Default — everything not matched below |
| LOW | False | 512 | "think about/through", "analyze/analyse", "explain why/how", "reason through", "figure out", "what do you think", "what would/if", "help me decide", "compare", "pros and cons", "difference between", "how/why does/is/are" |
| MED | False | 2048 | "really think", "think hard/carefully/deeply", "take your time", "be thorough" |
| HIGH | False | 8192 | "max thinking/effort", "think really hard", "this is important", "don't/dont fuck/mess this up", "give it everything", "full effort" |

Note: "should i" intentionally REMOVED from LOW triggers (too broad, catches dinner questions)
AgentLoop._classify_task() uses SEPARATE keywords: reason/analyze → "reasoning" task

Per-capability minimum max_tokens (_CAPABILITY_MIN_TOKENS in wake_listener.py):
Applied when a voice model override is active — ensures reasoning models have room for <think> chains.
Overrides the think level floor if it's lower; HIGH think (8192) always wins.

- reasoning/analysis/ministral_reasoning → 2048
- ministral/ministral_vision/code → 1024
- heavy_code → 2048
- all others (no override key) → 512 floor

---

## TOOL SYSTEM (direct dispatch patterns in wake_listener.py)

### Direct Dispatch (_try_direct_dispatch in wake_listener.py)

Layer 1 — bypasses AgentLoop entirely for common voice patterns:

| Pattern | Tool called |
|---|---|
| "web search for X", "web search X", "do a search for X", "search the word X", regex `\bsearch\b` catch-all, "search for X", "look up X", "google X", "find out X" | web_search(query) — AgentLoop safety net also forces web_search if tool_outputs empty + "search" in query |
| Weather/news regex patterns | web_search(transcription) |
| 10 screen regex patterns (see below) | take_screenshot() → **vision fast-path** |
| "clipboard" + read keywords | clipboard_read() |
| "copy X to clipboard" | clipboard_write(text) |
| "open https://..." | open_url(url) |
| "what's my X" / "what is my X" | memory_recall(fact_name) |
| "git status/diff/log" | git_* tools |
| "port NNNN", "chatterbox running" | check_port() |
| "list processes", "what's running" | list_processes() |

### Screen Trigger Patterns (10 regex, wake_listener.py ~line 120)

```python
screen_patterns = [
    r"what(?:'s| is| am i seeing| do you see| can you see) on (?:my |the )?screen",
    r"what(?:'s| is) on (?:my |the )?display",
    r"what am i (?:looking|staring) at",
    r"describe (?:my |the |what(?:'s| is) on (?:my |the )?)?screen",
    r"(?:look|looking) at (?:my |the )?screen",
    r"(?:see|read|tell me about) (?:my |the )?screen",
    r"what(?:'s| is) (?:this|that) on (?:my )?screen",
    r"take a (?:screen ?shot|screenshot)",
    r"screen ?shot",
    r"what(?:'s| is) (?:on )?(?:my )?(?:screen|display|monitor)",
]
```

### Tool Registry (agent/core/tool_registry.py)

Wired to TOOL_IMPLEMENTATIONS in agent/core/tools.py
execute(name, params) → {success, result/error, screenshot_path?}

### 28 Tools in tools.py

Categories: code execution, file system, git, memory, system, web, screen/UI
Key implementations:

- _web_search(): ddgs (duckduckgo-search) — confirmed working
- _take_screenshot(): ScreenObserver().observe() → returns screenshot_path even on HTTP failure
- _clipboard_read/write(): win32clipboard — confirmed working
- _memory_recall(): MemoryManager queries named_facts — confirmed working
- _list_processes(): WMI query — confirmed working
- _git_*(): subprocess git CLI calls

### Web Search Status

- Working: direct dispatch fires, ddgs queries live, results returned
- tool_context ASCII-stripped before injection (degree symbols were breaking model)
- RUST_LOG=warn set in run_wake_listener.py to suppress primp TLS debug spam

### Screen Observation Status — ✅ WORKING (2026-04-01)

- take_screenshot() fires correctly via 10 regex patterns
- Screenshot saved to workspace/screenshots/ as PNG
- screenshot_path returned even when HTTP vision API fails (endpoint is "local://llama_cpp")
- Vision fast-path in wake_listener loads image, resizes, base64-encodes, sends to Qwen3-VL-8B
- Image bytes reach LLM via create_chat_completion() + Qwen25VLChatHandler + mmproj
- Verified: describes actual screen content (not generic "I can't see your screen")

---

## MEMORY SYSTEM

SQLite DB: agent/core/memory/roamin_memory.db (gitignored)
ChromaDB: agent/core/memory/chroma_db/ (gitignored)

Tables: conversation_history, named_facts, actions_taken, observations, user_patterns

Fact extraction triggers: "remember my X is Y", "my X is Y", "save/note that my X is Y"
Memory injection: ONLY inject facts whose fact_name appears in the query text

---

## TIMING PROFILE (measured 2026-04-02 — post-latency-pass)

| Phase | Observed | Notes |
|---|---|---|
| Warmup (subsequent boots) | ~10s | 13 phrases loaded from disk |
| Wake phrase (cached) | ~2.7s | From WAV file |
| STT (VAD + Whisper CUDA) | ~0.5-1s | Whisper CUDA (commit a47b2f2) |
| Vision fast-path dispatch | ~0.5s | screenshot + PIL + base64 encode |
| Vision reply generation | ~7s | Qwen3-VL-8B with mmproj |
| Text reply generation | ~0.5-2s | Qwen3-VL-8B text-only |
| TTS — novel reply (Chatterbox) | ~8-26s | **BOTTLENECK — no streaming yet** (timeout cap 33s) |
| TTS — cached phrase | instant | WAV playback |
| **TOTAL (vision path)** | **~15-25s** | STT fixed; TTS remaining bottleneck |
| **TOTAL (text direct dispatch)** | **~5-8s** | e.g. weather/web search |

VRAM budget (24GB RTX 3090):

- Qwen3-VL-8B abliterated full offload: ~5.4GB (model 4.7GB + mmproj 718MB)
- Chatterbox TTS (CUDA): ~3GB
- Remaining when both loaded: ~15.6GB headroom
- Old Qwen3 8B was ~14GB — upgrade freed ~9GB VRAM

---

## CURRENT PHASE STATUS

| Phase | Status | Description |
|---|---|---|
| 1 — Stabilization | ✅ COMPLETE | AgentLoop execution, thread guard, warmup timeout |
| 1.5 — Resilience | ✅ COMPLETE | Tool timeouts, HTTP retry, dispatch fallback, input validation |
| 2 — Vision | ✅ COMPLETE | Image bytes pipeline, Qwen3-VL-8B, mmproj, vision fast-path |
| 3 — Latency | **IN PROGRESS** | 3A (Whisper CUDA) ✅ 3C (voice model select) ✅; 3B (streaming TTS) remaining |
| 3.5 — Model Discovery | ✅ COMPLETE | Standalone filesystem GGUF scan; no LM Studio/Ollama server required |
| 4 — Task Robustness | Planned | Deduplication, prioritization |
| 5 — UX & Plugins | Planned | Plugin system, notifications, RoaminCP |
| 6 — Security | Planned | API keys, LLM proxy, browser automation |

**Phase 3 remaining work:**

- **Streaming TTS (3B)** (HIGH complexity) — sentence-chunked synthesis, first words spoken much sooner

---

## KEY COMMITS (all sessions)

| Commit | What |
|---|---|
| 0886765 | Memory recall — fact extraction, context injection, get_all_named_facts |
| ef48a7e | TTS phrase cache — 13 phrases pre-generated as WAV at startup |
| 09ea011 | Wake phrase tuned synthesis params, per-phrase PHRASE_PARAMS |
| 790f4ae | Wake phrase changed to "yes? how can i help you" |
| 8a7223e | Three-tier think mode OFF/LOW/MED/HIGH |
| 3468fb0 | Fix AgentLoop reasoning triggers (removed think/why/explain) |
| be81473 | GPU unload before TTS + relevant-only memory injection |
| dccd5c5 | Remove "should i" from LOW think triggers, strip emojis |
| 6fdb2cb | torch.cuda.empty_cache() after llama unload |
| 4932fc9 | Reverted to full GPU offload (-1 layers) |
| 01464d2 | Claude Code context pack |
| 3644857 | ASCII strip on tool_context, RUST_LOG=warn |
| da78d21 | Wire all models including Ministral 14B, Mistral prompt format |
| a9eee05 | fix: reduce HTTP fallback timeout 60s→5s |
| 54cd6de | Pre-vision-upgrade backup |
| 88a0905 | Upgrade to Qwen3-VL-8B abliterated + CAPABILITY_MAP + model_config |
| 2d571b5 | Wire vision image bytes: chat_handler, multimodal branch, wake_listener fast-path |
| e63dcef | Expand screen triggers (regex) + fix screenshot_path on HTTP failure |
| a47b2f2 | Enable Whisper CUDA — STT 9-12s → ~0.5s |
| 4cf8449 | Fix torch CUDA availability check in stt.py |
| a488a30 | Fix TTS fallback: SAPI subprocess for non-main-thread calls |
| 90ceb59 | Add terminal monitoring window (python.exe + style=1 VBScript) |
| dbf4f2f | Auto-launch Chatterbox in VBScript, add IsChatterboxRunning() |
| 98b39bb | Fix web search hallucination + TeeStream terminal output |
| e07adf0 | Extend Chatterbox TTS synthesis timeout from 25s to 33s |
| de821d6 | docs: update context pack and priorities after Phase 3A + bug-fix session |
| 85e022a | feat: replace model name alias list with difflib fuzzy matching in _detect_model_override |
| 6130c2d | fix: WMI guard checks python.exe + pythonw.exe; double Chatterbox wait timeout to 120s |
| bc3615a | fix: remove LM Studio dependency from _start_silent.vbs |
| 4790a2f | fix: per-capability n_ctx and max_tokens floors for reasoning/code models |
| 90eec34 | fix: move RUST_LOG=warn before imports to silence primp/ddgs TLS debug spam |
| (session) | feat: standalone filesystem model discovery — model_sync.py full rewrite; drive walk + LM Studio scan + Ollama manifest resolver; model_router.py file_path dispatch; model_config.json model_scan_dirs + file_path; 13 tests passing; 6 models auto-registered on first run |

---

## WHAT STILL NEEDS WORK (Phase 3 priorities)

### Model Infrastructure

✅ **Standalone filesystem discovery (3.5)** — COMPLETE (2026-04-03)

- `model_sync.py` runs at startup; walks drives for `models/` dirs + `~/.lmstudio/models/` + Ollama blob manifest resolution
- Idempotent: first run adds new GGUFs, subsequent runs add 0
- `model_router.py` dispatches via `file_path` in config → `LlamaCppBackend` directly (no LM Studio/Ollama needed)
- `model_scan_dirs: []` in `model_config.json` — add extra dirs here if needed
- Drop a `.gguf` into any `models/` folder → registered on next Roamin restart automatically

### Latency (PRIMARY — blocks daily usability)

1. ✅ **Whisper CUDA** — COMPLETE (commit a47b2f2) — STT now ~0.5-1s on CUDA
2. ✅ **Model selection voice control (3C)** — COMPLETE (commits 85e022a, 4790a2f)
   - difflib fuzzy matching replaces 36-entry alias list
   - "use ministral/deepseek to X" → routes to correct model for that request only
   - Per-capability n_ctx (32768 for reasoning/ministral) and max_tokens floors (2048) applied

3. **Streaming TTS (3B)** — biggest remaining perceived latency win
   - Novel replies take 8-26s of silence before first word
   - Approach: sentence-split reply → synthesize + play sentence 1 while generating rest
   - Files: `model_router.py`, `tts.py`, `wake_listener.py`

### Architecture (SECONDARY)

4. **Task deduplication** — no protection against same query queued twice in AgentLoop
2. **Feature readiness checks** — pre-flight for vision deps (PIL, mmproj exists)

### Deferred Features (user-requested, not yet planned)

6. **Cancel/stop mid-generation** — abort a slow or wrong generation with ctrl+space
2. **Print thinking to terminal** — stream `<think>` tokens to terminal in real-time (related to 3B)

---

## OPERATING RULES (non-negotiable for this project)

1. PS5.1 ONLY — no &&, no ||, no ?:, no here-strings
2. Python changes: py_compile + flake8 --max-line-length=120 + pre-commit before commit
3. One atomic change at a time — validate before next change
4. No hardcoded absolute paths in Python — use Path(**file**).parent
5. No debug print() in committed code
6. Commit message must be in quotes inside a .bat file if it has spaces
7. File editing in PS5.1: use [System.IO.File]::ReadAllText/WriteAllText with full absolute paths
8. .gitignore covers: .claude/, workspace/, phrase_cache/, *.db,*.sqlite, _.bak_, logs/
9. black reformats on pre-commit: always re-add the file and commit again
10. Stale state: always read from disk — don't rely on cached file content

---

## SHELL PATTERNS THAT WORK

# Kill and restart Roamin (PS5.1)

Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like "*run_wake_listener*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Remove-Item "C:\AI\roamin-ambient-agent-tts\logs\_wake_listener.lock" -Force -ErrorAction SilentlyContinue
"" | Out-File "C:\AI\roamin-ambient-agent-tts\logs\wake_listener.log" -Encoding utf8
Start-Sleep -Seconds 2
Start-Process wscript.exe -ArgumentList '"C:\AI\roamin-ambient-agent-tts\_start_wake_listener.vbs"' -WindowStyle Hidden

# Monitor log (filtered — no TLS spam)

function Watch-Roamin {
    Get-Content C:\AI\roamin-ambient-agent-tts\logs\wake_listener.log -Wait -Tail 20 |
    Where-Object { $_ -notmatch "DEBUG - (send frame|received frame|encoding|connecting|connected|Browser emulation|Cipher|handshake|ALPN|TLS|binding|pooling|inserting|Using cipher|Not resuming|Final cipher)" }
}

# VRAM check

nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv,noheader

# Validate Python

C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python.exe -m py_compile file.py
C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python.exe -m flake8 file.py --max-line-length=120

# File edit in PS5.1 (use full paths)

$file = "C:\AI\roamin-ambient-agent-tts\agent\core\voice\wake_listener.py"
$content = [System.IO.File]::ReadAllText($file)
$content = $content.Replace('old text', 'new text')
[System.IO.File]::WriteAllText($file, $content)

---

## KNOWN GOTCHAS

- Whisper FP16 warning: harmless but means CPU FP32 — GPU not being used for STT
- pyttsx3 COM thread affinity: skips playback when not on main thread (prints log, continues)
- Chatterbox 500: VRAM contention — rare now that Qwen3-VL-8B only uses 5.4GB vs old 14GB
- LM Studio plugin: permanently installed, auto-loads, no shortcut needed
- RUST_LOG=warn set at top of run_wake_listener.py BEFORE all imports — Rust extensions (primp)
  read this env var at initialization time; setting it in main() is too late
- h2, hpack, httpcore added to Python noisy-logger suppression list (second-layer catch)
- ddgs (duckduckgo-search renamed package): install both for compatibility
  pip install ddgs duckduckgo-search
- pre-commit black reformats: causes commit to fail, re-add and try again
- Log file auto-prunes at 40KB max (keeps 15KB tail) — at startup + every 10 min
- Tool execution timeout: 30s per tool in AgentLoop; subprocess tools have own 30s timeout
- HTTP retry: model_router retries Timeout/ConnectionError 2x with exponential backoff (1s, 2s)
- vision endpoint in model_config.json is "local://llama_cpp" — NOT an HTTP URL
  ScreenObserver._send_to_vision_api() will always fail (ConnectionError) — this is expected
  Vision works via wake_listener fast-path (image bytes), NOT ScreenObserver HTTP path
- Vision TTS is slow (8-26s) because novel descriptions aren't cached — Phase 3B (streaming TTS) will fix this
- Keyboard 500ms debounce: prevents OS keyboard bounce from firing 3+ parallel wakes (suppress=True + interval=0.5s)
- TeeStream: stdout/stderr tee to both console (visible terminal) and log file — do NOT replace _TeeStream with a plain redirect or terminal goes blank
- Chatterbox timeout cap: 33s max — formula is min(15 + len(text)//10, 33); increase if very long replies still truncate
- VBScript auto-launch: IsChatterboxRunning() checks ports 4123-4129 via MSXML2.XMLHTTP; WaitForChatterbox loops 24×5s (120s max) after launching _start.bat — doubled from 60s for CUDA cold-start
- _start_silent.vbs: LM Studio dependency removed — now just 10s boot delay then launches _start.bat
- IsProcessRunning() WMI: checks BOTH python.exe AND pythonw.exe — Roamin runs as python.exe (visible terminal) so old pythonw.exe-only check was blind to it
- Per-capability n_ctx: reasoning/ministral load with n_ctx=32768, code with 16384, default with 8192. The n_ctx_seq < n_ctx_train warning for Qwen3-VL-8B is INTENTIONAL (VRAM budget)
- MCP server stability: NEVER use Windows-MCP PowerShell tool to kill Python processes — it crashes the MCP server. Use Bash tool with: taskkill //F //IM python.exe
