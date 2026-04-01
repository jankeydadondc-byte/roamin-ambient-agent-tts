# Roamin Ambient Agent — Master Context Pack
# Updated: 2026-04-01 (resilience pass — timeouts, retry, fallback, input validation)
# For: new Claude conversations to pick up where we left off
# Repo: C:\AI\roamin-ambient-agent-tts
# GitHub: jankeydadondc-byte/roamin-ambient-agent-tts (private)
# Latest commit: a9eee05 (pending: stabilization + resilience pass)

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
- Can execute tools: web search, clipboard, processes, memory recall, screenshots
- Architecture: ctrl+space → STT → direct dispatch OR AgentLoop → LLM → TTS

---

## REPO STRUCTURE

C:\AI\roamin-ambient-agent-tts\
├── run_wake_listener.py           # Entry point, RUST_LOG=warn, lock guard, warmup, log pruning
├── _start_wake_listener.vbs       # Windows startup launcher (lock file + WMI dual guard)
├── _launch_and_monitor.ps1        # Kill dupes, clear log, launch, tail filtered log
├── CONSOLIDATED_PRIORITIES.md     # Unified roadmap (merged still-needs-work + improvement batch)
├── CLAUDE_CODE_CONTEXT.md         # Previous context pack (superseded by this file)
├── agent/
│   └── core/
│       ├── voice/
│       │   ├── wake_listener.py   # Main orchestration: hotkey→STT→dispatch→LLM→TTS
│       │   ├── tts.py             # Chatterbox + pyttsx3 fallback, phrase cache
│       │   └── stt.py             # Silero VAD + Whisper CPU
│       ├── llama_backend.py       # LlamaCppBackend, ModelRegistry singleton, ALL models
│       ├── model_router.py        # Task→model routing, HTTP fallback w/ retry
│       ├── agent_loop.py          # Plan + execute loop (cancellation, per-step timeouts)
│       ├── tools.py               # 28 tool implementations (input validation, structured errors)
│       ├── tool_registry.py       # Tool plugin system wired to tools.py
│       ├── memory/
│       │   ├── memory_store.py    # SQLite CRUD + get_all_named_facts
│       │   ├── memory_search.py   # ChromaDB semantic search
│       │   └── memory_manager.py  # Unified interface
│       ├── screen_observer.py     # PIL screenshot + vision model
│       └── context_builder.py    # Builds context for AgentLoop
├── logs/
│   ├── wake_listener.log          # All stdout/stderr (auto-pruned 40KB max / 15KB tail)
│   └── startup.log                # VBS startup events
└── .gitignore                     # Includes .claude/, workspace/, phrase_cache/, *.db

---

## FULL MODEL REGISTRY (llama_backend.py CAPABILITY_MAP)

| Capability key(s) | Model | File size | VRAM | Notes |
|---|---|---|---|---|
| default, chat, fast | Qwen3 8B Q4 | 4.9GB | ~14GB | Default voice — 83 t/s |
| vision, screen_reading | Qwen3.5 9B Q4 + mmproj | 5.2GB + 0.9GB | ~6GB | Has vision projector |
| reasoning, analysis | DeepSeek R1 8B Q4 | 4.7GB | ~5GB | Deep think tasks |
| ministral, ministral_reasoning | Ministral 3 14B Q4 | 7.7GB | ~8GB | Vision + reasoning |
| ministral_vision | Ministral 3 14B Q4 + mmproj | 7.7GB + 0.8GB | ~9GB | Ministral with screen |
| code, heavy_code | Qwen3 Coder Next 80B Q4 | 45.2GB | >24GB | CPU offload only |

Model paths (all GGUF, all validated at runtime):
- Qwen3 8B: C:\Users\Asherre Roamin\.ollama\models\blobs\sha256-a3de86cd...
- Qwen3.5 9B: ..\.lmstudio\models\lmstudio-community\Qwen3.5-9B-GGUF\Qwen3.5-9B-Q4_K_M.gguf
- Qwen3.5 mmproj: ..\.lmstudio\models\lmstudio-community\Qwen3.5-9B-GGUF\mmproj-Qwen3.5-9B-BF16.gguf
- DeepSeek R1: ..\.lmstudio\models\DeepSeek-R1-0528-Qwen3-8B-Q4_K_M.gguf
- Ministral 14B: ..\.lmstudio\models\lmstudio-community\Ministral-3-14B-Reasoning-2512-GGUF\Ministral-3-14B-Reasoning-2512-Q4_K_M.gguf
- Ministral mmproj: ...same dir...\mmproj-Ministral-3-14B-Reasoning-2512-F16.gguf
- Qwen3 Coder: ..\.lmstudio\models\lmstudio-community\Qwen3-Coder-Next-GGUF\Qwen3-Coder-Next-Q4_K_M.gguf

Prompt formats (auto-detected from model path):
- Qwen3/DeepSeek: ChatML (<|im_start|> tokens), with no_think=True injects <think>\n\n</think>
- Ministral/Mistral: [INST] ... [/INST] format

n_gpu_layers=-1 (full GPU offload), n_ctx=8192
llama-cpp-python built with VS2019 + CUDA 13.1 + Ninja


---

## WINDOWS STARTUP CHAIN (clean as of this session)

Startup folder: C:\Users\Asherre Roamin\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\

| Shortcut | Target | Notes |
|---|---|---|
| Roamin-Chatterbox.lnk | C:\AI\chatterbox-api\_start_silent.vbs | ✅ Active |
| Roamin-ControlAPI.lnk | C:\AI\os_agent\_start_control_api.vbs | ✅ Fixed (native XMLHTTP) |
| Roamin-WakeListener.lnk | C:\AI\roamin-ambient-agent-tts\_start_wake_listener.vbs | ✅ Active |

Items REMOVED this session:
- Roamin-LMS-Plugin.lnk → DELETED (pointed to missing _lms_dev_silent.vbs)
  LM Studio plugin now permanently installed via: lms dev -i -y
  Plugin location: C:\Users\Asherre Roamin\.lm-studio\plugins\roamin-python-tools\
  Auto-loads with LM Studio. No startup shortcut needed.

Chatterbox TTS:
- Location: C:\AI\chatterbox-api
- Port: 4123, DEVICE=cuda (in .env)
- Voice sample: C:\AI\chatterbox-api\voice-sample.mp3 (Shawn James clone)
- venv: Python 3.12, torch 2.6.0+cu124

---

## VOICE PIPELINE (wake_listener.py _on_wake flow)

1. ctrl+space fires → _on_wake_thread → _on_wake
2. Speak cached wake phrase: "yes? how can i help you" (~2.7s from cache)
3. STT: Silero VAD listens → stops on silence → Whisper transcribes (~5-6s CPU)
4. Memory: _extract_and_store_fact() → regex-extract facts → write to named_facts
5. Memory: _build_memory_context() → only inject facts whose name appears in query
6. Layer 1 — Direct dispatch: _try_direct_dispatch(transcription, registry)
   - Pattern-matches against known tool intents
   - If match AND success: use tool result as context, skip AgentLoop
   - If match AND failure: FALL THROUGH to AgentLoop (resilience pass)
   - Returns dict with {success, result} or None
7. Layer 2 — AgentLoop (if no direct match OR direct dispatch failed):
   - _classify_task() → vision/code/reasoning/default
   - _generate_plan() → LLM returns JSON steps
   - _execute_step() → registry.execute() per step (30s timeout per tool)
   - cancel() method + threading.Event for graceful mid-plan cancellation
8. tool_context: ASCII-stripped, max 1500 chars
9. Think tier: _classify_think_level() → (no_think, max_tokens)
10. Reply: router.respond("default", ..., messages, max_tokens, no_think)
11. Strip <think> blocks, strip non-ASCII (emojis), truncate to 200 chars
12. TTS: speak(reply) — cache hit = instant, miss = Chatterbox synthesis (~12-22s)
13. Store conversation to memory

---

## TTS PHRASE CACHE

Location: agent/core/voice/phrase_cache/ (gitignored, regenerated at warmup)
warm_phrase_cache() called at startup — skips already-cached WAV files

13 pre-generated phrases with MD5-hashed filenames:
1.  "yes? how can i help you"     exaggeration=0.6, cfg_weight=0.4
2.  "Done."
3.  "Sorry, I didn't catch that."
4.  "Working on it."
5.  "The agent loop failed to complete that task."
6.  "That action needs your approval."
7.  "Got it."                     exaggeration=0.6, cfg_weight=0.4
8.  "I ran into an unexpected error, something fucked up while processing that."
9.  "On it."                      exaggeration=0.6, cfg_weight=0.4
10. "I'm not sure about that one."
11. "Give me a second."
12. "Anything else?"
13. "I didn't find anything about that."

Chatterbox 500 errors: retry once → pyttsx3 fallback
VRAM issue: Qwen3 8B + Chatterbox both on CUDA = contention
  Layer reduction (31/28 layers) tests showed no net gain
  Current approach: full GPU offload for LLM, Chatterbox gets VRAM after reply

---

## THREE-TIER THINK MODE (_classify_think_level in wake_listener.py)

| Tier | no_think | max_tokens | Triggers |
|---|---|---|---|
| OFF | True | 60 | Default — everything not matched below |
| LOW | False | 512 | "think about/through", "analyze/analyse", "explain why/how", "reason through", "figure out", "what do you think", "what would/if", "help me decide", "compare", "pros and cons", "difference between", "how/why does/is/are" |
| MED | False | 2048 | "really think", "think hard/carefully/deeply", "take your time", "be thorough" |
| HIGH | False | 8192 | "max thinking/effort", "think really hard", "this is important", "don't/dont fuck/mess this up", "give it everything", "full effort" |

Note: "should i" was intentionally REMOVED from LOW triggers (too broad, catches dinner questions)
AgentLoop._classify_task() uses SEPARATE keywords: reason/analyze → "reasoning" task
  This was a bug: "think about dinner" triggered DeepSeek model swap
  Fix: removed "think", "why", "explain" from AgentLoop's reasoning triggers

---

## TOOL SYSTEM (added this session via Claude Code worktree)

### Direct Dispatch (_try_direct_dispatch in wake_listener.py)
Layer 1 — bypasses AgentLoop entirely for common voice patterns:

| Pattern | Tool called |
|---|---|
| "search for X", "look up X", "google X", "find out X" | web_search(query) |
| Weather/news regex patterns | web_search(transcription) |
| "what's on my screen", "what am i looking at", etc. | take_screenshot() |
| "clipboard" + read keywords | clipboard_read() |
| "copy X to clipboard" | clipboard_write(text) |
| "open https://..." | open_url(url) |
| "what's my X" / "what is my X" | memory_recall(fact_name) |
| "git status/diff/log" | git_* tools |
| "port NNNN", "chatterbox running" | check_port() |
| "list processes", "what's running" | list_processes() |

### Tool Registry (agent/core/tool_registry.py)
Wired to TOOL_IMPLEMENTATIONS in agent/core/tools.py
execute(name, params) → {success, result/error}

### 28 Tools in tools.py
Categories: code execution, file system, git, memory, system, web, screen/UI
Key implementations:
- _web_search(): ddgs (duckduckgo-search) — confirmed working
- _take_screenshot(): ScreenObserver().observe() — fires but vision routing incomplete
- _clipboard_read/write(): win32clipboard — confirmed working
- _memory_recall(): MemoryManager queries named_facts — confirmed working
- _list_processes(): WMI query — confirmed working
- _git_*(): subprocess git CLI calls

### Web Search Status
- Working: direct dispatch fires, ddgs queries live, results returned
- tool_context ASCII-stripped before injection (degree symbols were breaking model)
- RUST_LOG=warn set in run_wake_listener.py to suppress primp TLS debug spam
  (primp is Rust-based, bypasses Python logging — env var set before redirect)

### Screen Observation Status
- take_screenshot() fires correctly
- Screenshot saved to workspace/screenshots/
- BUG: result passed as text to default model which can't see images
- FIX NEEDED: route to vision/ministral_vision capability with actual image bytes


---

## MEMORY SYSTEM

SQLite DB: agent/core/memory/roamin_memory.db (gitignored)
ChromaDB: agent/core/memory/chroma_db/ (gitignored)

Tables: conversation_history, named_facts, actions_taken, observations, user_patterns

Fact extraction triggers: "remember my X is Y", "my X is Y", "save/note that my X is Y"
Memory injection: ONLY inject facts whose fact_name appears in the query text
  (prevents blue food hallucinations when asking about dinner)

Methods added this session:
- MemoryStore.get_all_named_facts() — added, used by _build_memory_context

Known stored facts:
- favorite color: blue (confirmed working — "my favorite color is blue" → stored → recalled)

---

## TIMING PROFILE (measured during this session)

| Phase | Time | Notes |
|---|---|---|
| Warmup (first boot) | ~36s | 13 phrases generated from scratch |
| Warmup (subsequent) | ~12s | 13 phrases loaded from disk |
| Wake phrase (cached) | ~2.7s | From WAV file |
| STT (VAD + Whisper) | ~5-6s | CPU, FP32 |
| AgentLoop (model hot) | ~3-4s | GPU already loaded |
| AgentLoop (model cold) | ~12-20s | Reloading after unload |
| Direct dispatch | ~0.1-1.7s | Web search ~1.5s, memory ~0.1s |
| Reply generation | ~0.1-1.5s | Qwen3 8B GPU |
| TTS novel reply | ~7-22s | Chatterbox CUDA synthesis |
| TTS cached phrase | instant | WAV playback |
| TOTAL (direct dispatch path) | ~13-16s | e.g. weather search |
| TOTAL (AgentLoop path) | ~20-37s | Complex queries |

VRAM budget (24GB RTX 3090):
- Qwen3 8B full offload: ~14GB
- Chatterbox TTS (CUDA): ~3GB
- Remaining when both loaded: ~7GB (was 0 = 500 errors)
- GPU unload + empty_cache() frees Chatterbox headroom but causes cold reload next wake

---

## WHAT WAS FIXED THIS SESSION (in order)

1. Memory recall broken → fixed _extract_and_store_fact + _build_memory_context
2. named_facts table empty → fact extraction regex now writes correctly
3. "Yes?" wake phrase sounded bad → changed to "yes? how can i help you"
4. Phrase cache not generating → warm_phrase_cache() wired into warmup
5. "Yes?" printed twice in log → duplicate log print + duplicate stt init removed
6. AgentLoop routing to DeepSeek for "think" queries → removed think/why/explain triggers
7. Chatterbox 500 VRAM errors → torch.cuda.empty_cache() after llama unload
8. Layer reduction test (31→28 layers) → no net gain, reverted to full -1
9. Chatterbox to CPU test → 22s synthesis, same as CUDA, reverted
10. Blue food hallucination → memory injection scoped to query-relevant facts only
11. Emoji in replies → re.sub non-ASCII strip on all model output
12. "should i" triggering LOW think tier for dinner questions → removed
13. GPU unload causing cold model reload next wake → REMOVED the unload entirely
14. Boot: VBS error popup → deleted Roamin-LMS-Plugin.lnk (target missing)
15. Boot: "Select app to open Asherre" → caused by #14, now fixed
16. Boot: terminal flash from ControlAPI → replaced PowerShell port check with XMLHTTP
17. LM Studio plugin not loading → lms dev -i -y permanently installs it
18. Claude Code worktree files in git → added .claude/ workspace/ to .gitignore
19. TLS/primp debug spam in log → RUST_LOG=warn in run_wake_listener.py
20. Web search tool_context garbled → ASCII encode before injection
21. Web search reply wrong → "couldn't find weather" fixed by ASCII strip
22. Tool files in wrong git paths → copied from worktree to correct locations

## STABILIZATION PASS (2026-03-31)

23. AgentLoop tool execution stub → wired registry.execute() in _execute_step()
    - Layer 2 was generating plans but NEVER running tools (comment said "wired in A5+")
    - Fixed: executes tool, sets status="executed", captures outcome[:1500]
    - wake_listener.py already filters for status=="executed" — no other changes needed
24. Thread guard on _on_wake → non-blocking lock in WakeListener
    - Rapid ctrl+space presses were spawning concurrent threads (VRAM/mic/TTS contention)
    - Fixed: _wake_lock = threading.Lock(), acquire(blocking=False) drops duplicate presses
    - Logs "[Roamin] Wake already in progress, ignoring" on dropped presses
25. Defensive memory context init → facts=[] initialized before try block
    - _build_memory_context() had fragile NameError risk if MemoryStore() threw
    - Fixed: facts=[] before try, filtering logic moved outside exception handler
26. LM Studio VRAM warning at warmup → port 1234 check before GPU load
    - User had no signal why GPU warmup failed when LM Studio occupied VRAM
    - Fixed: socket.create_connection("127.0.0.1", 1234, timeout=1) warns if detected
27. Warmup timeout guard → threaded 120s timeout on GPU model load
    - Corrupt GGUF or hung CUDA driver could block startup forever
    - Fixed: daemon thread + wt.join(timeout=120), logs TIMED OUT if hung

## RESILIENCE PASS (2026-04-01)

28. Double-launch race condition fixed in VBS launcher
    - _start_wake_listener.vbs now checks lock file PID BEFORE WMI scan
    - IsPidRunning() helper queries Win32_Process by PID directly
    - Covers the startup race window where WMI hasn't updated yet
29. AgentLoop graceful cancellation → cancel() method + threading.Event
    - _cancel_event checked between steps, returns status="cancelled"
    - wake_listener speaks "Got it, stopping." on cancellation
30. Per-step tool timeout → 30s via ThreadPoolExecutor in _execute_step()
    - Prevents a single stuck tool from hanging the entire AgentLoop
    - Logs warning with tool name on timeout
31. HTTP retry with exponential backoff in ModelRouter
    - Timeout/ConnectionError retries 2x (1s, 2s delays)
    - Logs each retry attempt with reason
    - KeyError (bad response format) still fails immediately
32. Direct dispatch fallback → failed tools fall through to AgentLoop
    - Previously: tool failure result was injected as context (bad reply)
    - Now: sets direct_result=None, AgentLoop runs as if no pattern matched
33. Input validation on security-critical tools
    - open_url, fetch_url: reject non-http(s) schemes
    - web_search: strip control chars, 500 char limit
    - clipboard_write: strip null bytes, 10k char limit
    - run_python, run_powershell, run_cmd: 10k char limit
34. Structured error categories in _fail()
    - _fail() accepts optional category: "validation", "timeout", "unavailable", "permission", "error"
    - Enables downstream consumers to differentiate error types
35. Log auto-pruning reduced from 500KB to 40KB max (15KB tail)
    - Keeps log under ~10k tokens for readability
    - Prunes at startup + every 10 minutes via background thread

---

## WHAT STILL NEEDS WORK (next session priorities)

See also: CONSOLIDATED_PRIORITIES.md for the full unified roadmap (Priorities 1-7).

### Critical / Functional
1. Screen observation vision routing (CONSOLIDATED_PRIORITIES.md Priority 2)
   - take_screenshot() fires, ScreenObserver.observe() sends to vision API internally
   - BUT: when routed back through wake_listener, result is text passed to default model
   - FIX: detect screenshot result in direct dispatch → re-route to task='vision' with image bytes
   - llama_backend.chat() has NO image handling currently — needs extension
   - Pass actual image bytes to llama_backend chat() with vision model + mmproj loaded

2. Model selection — no voice-controlled way to pick model
   - Current: hardcoded in CAPABILITY_MAP, auto-selected by keyword
   - Options: A) voice trigger words ("use ministral"), B) memory preference,
     C) query prefix ("ministral: what's on my screen")
   - Ministral 14B capabilities registered but nothing routes to them yet

### Latency
3. Streaming TTS
   - Biggest remaining latency win (~50% cut to perceived response time)
   - Pipe model output token-by-token to Chatterbox as sentences complete
   - Requires rewriting router.respond() to yield tokens
   - Chatterbox /v1/audio/speech likely does NOT support streaming (OpenAI-compat)
   - model_router.respond() returns str, both backends set stream: False

4. Whisper CUDA
   - STT takes 5-6s on CPU
   - Options: install CUDA torch (~3GB), or switch to whisper.cpp
   - Would cut STT to ~0.5s

### Architecture
5. RoaminCP UI (C:\AI\os_agent\ui\roamin-control)
   - Tauri + React, Monaco editor, xterm terminal, diff viewer
   - Not yet connected to ambient agent
   - Control API still points at os_agent, not new repo

6. TurboQuant KV cache compression
   - Evaluated — deferred until package matures
   - Would free ~1-4GB VRAM during inference
   - Requires migrating from llama-cpp-python to HuggingFace or vLLM
   - Current package version: 0.2.0 alpha (released 2026-03-27)

### Cosmetic
7. primp TLS debug spam in logs during web_search
   - RUST_LOG=warn set but primp bypasses it for ddgs HTTP connections
   - _launch_and_monitor.ps1 filters it out of terminal view
   - Log auto-prune keeps file small, but spam still fills ~90% of log content

---

## KEY COMMITS THIS SESSION

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
| cbf593a | Layer reduction test 32 layers (reverted) |
| c44d663 | Chatterbox CPU test (reverted) |
| 5135784 | Layer test 31 layers |
| e60a947 | Layer test 28 layers |
| 4932fc9 | Reverted to full GPU offload (-1 layers) — layer tests concluded |
| 01464d2 | Claude Code context pack (CLAUDE_CODE_CONTEXT.md) |
| 1b09a83 | Tool files placed in correct repo paths |
| b598dd8 | Remove GPU unload before TTS, delete temp scripts |
| fdabf08 | Remove .claude worktrees from git, add to gitignore |
| 3644857 | ASCII strip on tool_context, RUST_LOG=warn |
| da78d21 | Wire all models including Ministral 14B, Mistral prompt format |
| a9eee05 | fix: reduce HTTP fallback timeout 60s→5s — prevents hang when LM Studio closed |
| (pending) | fix: stabilization pass — AgentLoop execution, thread guard, warmup timeout, LM Studio warning |
| (pending) | feat: resilience pass — tool timeouts, HTTP retry, dispatch fallback, input validation, log prune 40KB |

---

## CLAUDE CODE WORKTREE NOTES (lessons learned)

Claude Code uses git worktrees at .claude/worktrees/[name]/
- .claude/ and workspace/ are now in .gitignore — won't pollute repo again
- Worktree files are NOT in the main working directory — copy them manually
- Use main repo venv for validation: C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python.exe
- After Claude Code session: git add -A from inside worktree, commit, then cd to main repo and merge
- Do NOT run git commit from main repo with worktree paths — files land in wrong location

---

## OPERATING RULES (non-negotiable for this project)

1. PS5.1 ONLY — no &&, no ||, no ?:, no here-strings
2. Python changes: py_compile + flake8 --max-line-length=120 + pre-commit before commit
3. One atomic change at a time — validate before next change
4. No hardcoded absolute paths in Python — use Path(__file__).parent
5. No debug print() in committed code
6. Commit message must be in quotes inside a .bat file if it has spaces
7. File editing in PS5.1: use [System.IO.File]::ReadAllText/WriteAllText with full absolute paths
8. .gitignore covers: .claude/, workspace/, phrase_cache/, *.db, *.sqlite, *.bak*, logs/
9. black reformats on pre-commit: always re-add the file and commit again
10. Stale state: sandbox /mnt/project/ files are outdated — always read from disk

---

## SHELL PATTERNS THAT WORK

# Kill and restart Roamin
Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like "*run_wake_listener*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Remove-Item "C:\AI\roamin-ambient-agent-tts\logs\_wake_listener.lock" -Force -ErrorAction SilentlyContinue
"" | Out-File "C:\AI\roamin-ambient-agent-tts\logs\wake_listener.log" -Encoding utf8
Start-Sleep -Seconds 2
Start-Process wscript.exe -ArgumentList '"C:\AI\roamin-ambient-agent-tts\_start_wake_listener.vbs"' -WindowStyle Hidden

# Monitor log (filtered)
Get-Content C:\AI\roamin-ambient-agent-tts\logs\wake_listener.log -Wait -Tail 20

# Filtered log (no TLS spam) — define as function
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

- Whisper FP16 warning: harmless, runs FP32 on CPU
- pyttsx3 COM thread affinity: skips playback when not on main thread (prints log, continues)
- Chatterbox 500: VRAM contention — Qwen3 fills GPU, Chatterbox can't allocate
- LM Studio plugin: permanently installed, auto-loads, no shortcut needed
- RUST_LOG=warn suppresses primp TLS spam at process level (set before stdout redirect)
- TLS debug spam still leaks through for ddgs web_search connections (~90% of log volume)
- ddgs (duckduckgo-search renamed package): install both for compatibility
  pip install ddgs duckduckgo-search
- Claude Code worktrees: always validate with main repo venv, copy files manually after
- pre-commit black reformats: causes commit to fail, re-add and try again
- Git commit with spaces in message: use .bat file or single-word message in inline cmd
- Log file auto-prunes at 40KB max (keeps 15KB tail) — at startup + every 10 min
- Tool execution timeout: 30s per tool in AgentLoop; subprocess tools have their own 30s timeout
- HTTP retry: model_router retries Timeout/ConnectionError 2x with exponential backoff (1s, 2s)
