# Roamin Consolidated Priorities — Unified Roadmap

**Date:** 2026-04-03 (updated after Phase 3C complete + token/context pass)
**Scope:** Merge "still needs work" items with Prioritized Improvement Batch into single coherent roadmap
**Focus:** Most important to stability and solid build first

---

## PRIORITY 1: CORE STABILITY & ERROR RESILIENCE

**Why first:** Without these, the agent can crash or hang unpredictably. Stability is the foundation.

### Already Fixed (Stabilization Pass — 2026-03-31)
- ✅ AgentLoop tool execution stub → wired `registry.execute()` in `_execute_step()`
- ✅ Thread guard on `_on_wake` → non-blocking lock prevents concurrent wake presses
- ✅ Defensive memory context init → `facts=[]` before try block
- ✅ LM Studio VRAM warning → port 1234 check at warmup
- ✅ Warmup timeout guard → 120s threaded timeout on GPU load

### Already Fixed (Resilience Pass — 2026-04-01)
- ✅ Double-launch race condition → VBS lock file PID check before WMI scan (`_start_wake_listener.vbs`)
- ✅ Graceful task termination → `AgentLoop.cancel()` + `threading.Event` checks between steps (`agent_loop.py`)
- ✅ Per-step tool timeout → 30s via `ThreadPoolExecutor` in `_execute_step()` (`agent_loop.py`)
- ✅ HTTP retry with exponential backoff → retries Timeout/ConnectionError 2x (1s, 2s) (`model_router.py`)
- ✅ Direct dispatch fallback → failed tools fall through to AgentLoop instead of injecting error as context (`wake_listener.py`)
- ✅ Structured error categories → `_fail()` accepts `category` param: validation/timeout/unavailable/permission/error (`tools.py`)
- ✅ Input validation on security-critical tools → URL scheme check, control char strip, size limits (`tools.py`)
- ✅ Log auto-prune reduced → 40KB max / 15KB tail (~10k tokens) (`run_wake_listener.py`)

### Also Fixed (Bug-Fix Pass — 2026-04-02)
- ✅ Web search hallucination — expanded direct dispatch triggers (13 phrasings), regex catch-all, AgentLoop safety net (`wake_listener.py`)
- ✅ Empty terminal window — `_TeeStream` tees stdout/stderr to both console and log file (`run_wake_listener.py`)
- ✅ Chatterbox not auto-launching — VBScript now checks ports + launches `_start.bat` (`_start_wake_listener.vbs`)
- ✅ TTS truncation on long replies — timeout cap extended 25s → 33s (`tts.py`)
- ✅ AgentLoop hallucination fallback — safety net forces `web_search` if plan executed no tools + "search" in query (`wake_listener.py`)
- ✅ AgentLoop system prompt strengthened — explicit MUST-use-tool mandate (`agent_loop.py`)

### Also Fixed (Phase 3C + Stability Pass — 2026-04-02/03)
- ✅ Duplicate process guard — WMI query now checks `python.exe OR pythonw.exe`; was blind to visible-terminal launches (`_start_wake_listener.vbs`)
- ✅ Chatterbox cold-start timeout — doubled from 60s to 120s; CUDA model load takes 90-120s; phrase cache was skipping → SAPI voice all session (`_start_wake_listener.vbs`)
- ✅ `_start_silent.vbs` LM Studio dependency — removed 20-line wait loop; replaced with 10s boot delay (`_start_silent.vbs`)
- ✅ Model selection voice control (Phase 3C) — `difflib` fuzzy matching replaces 36-entry Whisper alias list; two-stage detection catches garbles like "ministerial"→"ministral" at 0.72 cutoff (`wake_listener.py`)
- ✅ Per-capability n_ctx — reasoning/ministral now load with 32768 context (was 8192); eliminates context overflow on long `<think>` chains (`llama_backend.py`)
- ✅ Per-capability max_tokens floor — model overrides now apply 2048 floor for reasoning/ministral, 1024 for code; prevents `<think>` chain crowding out spoken answer (`wake_listener.py`)
- ✅ Rust TLS debug spam — `RUST_LOG=warn` moved before all imports; primp reads it at init time, not at `main()` call; `h2`/`hpack`/`httpcore` added to Python noisy-logger list (`run_wake_listener.py`)

### Remaining Gaps

#### 1. Plugin-Level Fallback Chains
- If a plugin/tool has an alternative method, automatically try it
- Currently only direct dispatch → AgentLoop fallback exists
- No tool-to-tool fallback within AgentLoop itself
- **Files:** `agent/core/agent_loop.py`, `agent/core/tool_registry.py`
- **Priority:** Low — not blocking daily use

**Impact:** Priority 1 is substantially complete. Remaining gap is incremental, not a blocker.

---

## PRIORITY 2: VISION CAPABILITY COMPLETION — ✅ COMPLETE

**Completed 2026-04-01** — full end-to-end image pipeline working.

### Verified Working (Manual test 2026-04-01 21:07)
- ✅ Screen observation fires via direct dispatch (expanded regex trigger patterns)
- ✅ Screenshot saved to `workspace/screenshots/` as PNG
- ✅ `_take_screenshot()` returns `screenshot_path` even when HTTP vision API fails
- ✅ Vision fast-path in `wake_listener.py` loads screenshot, PIL-resizes to 1024x1024, base64-encodes
- ✅ Multimodal message with `image_url` block sent to `router.respond("vision", messages=...)`
- ✅ `LlamaCppBackend.chat()` detects list-type content → routes to `create_chat_completion()`
- ✅ `Qwen25VLChatHandler` invokes mmproj vision encoder (PNG STREAM markers confirm)
- ✅ Qwen3-VL-8B-abliterated describes actual on-screen content:
  > *"You're looking at a code review interface where you're verifying test changes and planning to restart your development environment."*

### Key Commits (Vision Pass)
- `88a0905` — Model upgrade to Qwen3-VL-8B abliterated + CAPABILITY_MAP + model_config
- `2d571b5` — Wire vision image bytes: chat_handler, multimodal branch, wake_listener fast-path
- `e63dcef` — Expand screen triggers (regex) + fix screenshot_path return on HTTP failure

### Remaining (Non-Blocking)
- Feature readiness checks: pre-flight for vision deps (PIL, mmproj loaded)
- Capability-based access control (vision mode vs text-only queries)
- Both deferred to later pass — core vision works

---

## PRIORITY 3: LATENCY REDUCTION — NEXT FOCUS

**Why now:** Vision works but end-to-end time is 20-45s. This degrades daily usability significantly.
The base is functionally solid. Latency is the biggest remaining quality-of-life gap before adding features.

### Observed Timings (Post-Phase-3A, 2026-04-02)
| Phase | Observed | Target |
|---|---|---|
| Wake phrase (cached) | ~2.7s | ~2.7s ✅ |
| STT (VAD + Whisper CUDA) | ~0.5-1s | ~0.5s ✅ (Phase 3A complete) |
| Direct dispatch | ~0.5s | ~0.5s ✅ |
| Vision reply generation | ~7s | ~5s |
| Text reply generation | ~0.5-2s | ~0.5s ✅ |
| TTS (novel reply, Chatterbox) | ~8-26s | ~3-5s |
| **TOTAL (vision path)** | **~15-25s** | **~15s** |
| **TOTAL (text direct dispatch)** | **~5-8s** | **~5s** |

### 3A — Whisper CUDA ✅ COMPLETE (commit a47b2f2)
- **Result:** STT ~0.5-1s CUDA (was 9-12s CPU FP32)
- **VRAM cost:** ~500MB during STT, released after transcription
- **Files:** `agent/core/voice/stt.py`

### 3B — Streaming TTS (HIGH ROI, HIGH complexity)
- **Current:** Full LLM reply generated → THEN full Chatterbox synthesis → THEN playback
- **Problem:** User hears nothing for 8-26s after reply is ready
- **Opportunity:** Sentence-level chunking — synthesize first sentence while LLM generates rest
  - Split reply on `.`, `?`, `!` after first sentence (~10-20 tokens)
  - Begin Chatterbox synthesis of sentence 1 while model continues generating
  - Queue remaining sentences; play in order
- **Note:** `Chatterbox /v1/audio/speech` is OpenAI-compat — no true streaming
  - True streaming requires chunked HTTP response reading or websocket
  - Sentence-chunking is simpler and achieves ~60% of the latency win
- **Impact:** First words spoken ~5-8s earlier; perceived response feels near-instant
- **Complexity:** HIGH — requires `router.respond()` to yield tokens + sentence splitter + TTS queue
- **Files:** `agent/core/model_router.py`, `agent/core/voice/tts.py`, `agent/core/voice/wake_listener.py`
- **Recommendation:** Tackle AFTER Whisper CUDA (lower complexity first)

### 3C — Model Selection Voice Control ✅ COMPLETE (commits 85e022a, 4790a2f)
- **Result:** `_detect_model_override()` uses two-stage detection:
  1. Exact prefix match for multi-word phrases ("deep seek", "think hard about", etc.)
  2. `difflib.get_close_matches()` at 0.72 cutoff catches Whisper garbles (e.g. "ministerial"→"ministral")
- Routing is per-request only — no persistent state; defaults back after reply
- Reasoning/ministral overrides get n_ctx=32768 and min 2048 max_tokens
- Code overrides get n_ctx=16384 and min 1024 max_tokens
- Deferred features (not yet planned): cancel/stop mid-generation; print `<think>` to terminal in real-time

---

## PRIORITY 4: TASK EXECUTION ROBUSTNESS

**Why fourth:** Once latency is addressed, handle edge cases in task handling.

### Planned Enhancements

#### 1. Task Deduplication
- Prevent redundant execution if same intent queued multiple times rapidly
- Thread guard already blocks concurrent *wake presses*, but AgentLoop has no dedup
- **Files:** `agent/core/agent_loop.py`
- **Complexity:** LOW

#### 2. Dynamic Task Prioritization
- Priority-based queue system (high/medium/low)
- Can assign based on urgency keywords or user input
- **Files:** `agent/core/agent_loop.py`
- **Complexity:** MEDIUM

**Impact:** More reliable multi-task handling, prevents spamming agent with same request.

---

## PRIORITY 5: PLUGIN SYSTEM FOUNDATION

**Why fifth:** Enables future extensibility without breaking stability.

### Planned Enhancements

#### 1. Plugin Isolation and Sandboxing
- Run plugins in isolated environments (virtual threads with restricted access)
- Prevents one bad plugin from crashing the whole agent
- **Files:** `agent/core/plugin_loader.py` (new file)

#### 2. Plugin Security Basics
- Restrict file operations in plugins to specific directories
- **Files:** `agent/core/tool_registry.py`, `agent/core/plugin_loader.py`

#### 3. Structured Error Reporting for Plugins
- Plugin failures don't crash the agent, just emit errors
- **Files:** `agent/core/agent_loop.py`

**Impact:** Safe extensibility. Can add tools/plugins later without risking system stability.

---

## PRIORITY 6: USER EXPERIENCE ENHANCEMENTS

**Why sixth:** After stability and core features work, improve the experience.

### Planned Enhancements

#### 1. Real-Time Task Progress Updates
- Forward progress updates for long-running tasks
- Current web search gives no indication it's working
- **Files:** `agent/core/agent_loop.py`, `agent/core/voice/wake_listener.py`

#### 2. Notification System
- Toast notifications for task completion/failures/events
- Currently rely solely on TTS replies
- **Files:** `agent/core/voice/tts.py` (new notification layer)

#### 3. Task History and Logging
- Maintain history of executed tasks with timestamps, results
- **Files:** `agent/core/memory/memory_manager.py`

#### 4. RoaminCP UI Integration
- **Current state:** RoaminCP UI exists (Tauri + React, Monaco editor, xterm terminal, diff viewer)
  - Location: `C:\AI\os_agent\ui\roamin-control`
  - Not yet connected to ambient agent
  - Control API still points at os_agent, not new repo
- **Solution:** Wire RoaminCP to this repo's Control API, add websocket event streaming
- **Complexity:** MEDIUM-HIGH — cross-repo integration
- **Timeline:** After streaming TTS complete
- **Files:** `agent/core/api.py` (new), wiring to RoaminCP

**Impact:** Better user feedback, easier troubleshooting, more transparent operation.

---

## PRIORITY 7: SECURITY & INTEGRATION HARDENING

**Why seventh:** Once everything else works well, harden for production.

### Planned Enhancements

#### 1. API Key Management
- Secure management of credentials via environment variables/secrets manager
- **Files:** `agent/core/config.py`

#### 2. LLM Proxy Layer
- Normalize responses from different LLM providers
- **Files:** `agent/core/model_router.py` (refactor)

#### 3. Browser Automation
- Integrate Selenium/Playwright for web interactions
- Currently only have `web_search`, no browser control
- **Files:** `agent/core/tools.py` (new browser tools)

**Impact:** Production-ready security and broader capability set.

---

## EXECUTION ROADMAP (by phase)

### Phase 1: Stabilization ✅ COMPLETE
- ✅ Fix 5 critical bugs (Stabilization Pass — 2026-03-31)
- ✅ Test end-to-end voice flow
- ✅ Verify direct dispatch + AgentLoop both functional

### Phase 1.5: Resilience ✅ COMPLETE
- ✅ Double-launch VBS fix
- ✅ AgentLoop cancellation + 30s tool timeouts
- ✅ HTTP retry with exponential backoff
- ✅ Direct dispatch fallback to AgentLoop
- ✅ Input validation + structured error categories
- ✅ Log prune 40KB limit

### Phase 2: Vision ✅ COMPLETE (2026-04-01)
- ✅ Downloaded Qwen3-VL-8B abliterated (Q4_K_M, 4.7GB) + mmproj (Q8_0, 718MB)
- ✅ Updated CAPABILITY_MAP: default/chat/fast/vision/screen_reading → Qwen3-VL-8B
- ✅ chat_handler (Qwen25VLChatHandler) replaces raw mmproj= kwarg
- ✅ Multimodal branch in LlamaCppBackend.chat() → create_chat_completion()
- ✅ Vision fast-path in wake_listener: screenshot → base64 → image_url → vision LLM
- ✅ Expanded screen trigger regex patterns (8 substrings → 10 regex)
- ✅ _take_screenshot() returns screenshot_path on HTTP failure (no longer blocks fast-path)
- ✅ Manual test passed: describes actual on-screen content (21:07 2026-04-01)

### Phase 3: Latency (IN PROGRESS — 3B remaining)
**Goal:** Cut total response time from 20-45s to 10-20s
**Items:**
1. ✅ Whisper CUDA — STT 9-12s → ~0.5s (`stt.py` — commit a47b2f2)
2. ✅ Model selection voice control — difflib fuzzy matching, per-request routing, per-capability n_ctx/tokens (`wake_listener.py`, `llama_backend.py` — commits 85e022a, 4790a2f)
3. Streaming TTS — sentence-chunked synthesis (`model_router.py`, `tts.py`, `wake_listener.py`)

### Phase 4: Task Robustness
**Items:** Priority 4 (deduplication, prioritization)

### Phase 5: UX & Extensibility
**Items:** Priority 5 (plugins) + Priority 6 (UX, RoaminCP)

### Phase 6: Security Hardening
**Items:** Priority 7

---

## Priority by Stability Impact

### Critical (Block Reliable Daily Use)
- ✅ AgentLoop execution (FIXED — stabilization pass)
- ✅ Thread safety (FIXED — stabilization pass)
- ✅ Task timeouts + retry logic (FIXED — resilience pass)
- ✅ Input validation (FIXED — resilience pass)
- ✅ Structured error reporting (FIXED — resilience pass)
- ✅ Fallback mechanisms (FIXED — resilience pass)
- ✅ Double-launch race (FIXED — resilience pass)
- ✅ Vision pipeline end-to-end (FIXED — vision pass 2026-04-01)

### High (Improve Usability)
- ✅ **Whisper CUDA** — COMPLETE (9-12s → ~0.5s)
- ✅ **Model selection voice control** — COMPLETE (per-request routing via fuzzy match)
- **Streaming TTS** — 8-26s silent wait after reply ready

### Medium (Quality of Life)
- Task deduplication
- Plugin-level fallback chains
- Cancel/stop mid-generation (ctrl+space abort)
- Print `<think>` tokens to terminal in real-time

### Low (Nice-to-Have)
- Plugin system
- RoaminCP UI integration
- TurboQuant KV cache

---

## Success Criteria

**End of Phase 1.5 (Resilience): ✅ ACHIEVED**
- No hangs > 30s (tool timeouts fire) ✅
- API errors retry exponentially ✅
- Invalid inputs rejected gracefully ✅
- Failed direct dispatch falls through to AgentLoop ✅
- Rapid ctrl+space drops duplicate presses ✅

**End of Phase 2 (Vision): ✅ ACHIEVED**
- ✅ ctrl+space → "what's on my screen" returns actual screen description
- ✅ No false "can't see images" responses
- ✅ llama_backend.chat() handles image bytes with vision model + mmproj

**Phase 3A (Whisper CUDA): ✅ ACHIEVED**
- ✅ STT < 1s on every query (Whisper CUDA commit a47b2f2)

**Phase 3C (Model Voice Select): ✅ ACHIEVED**
- ✅ Voice can route to Ministral 14B or DeepSeek R1 per-request ("use ministral to X", "use deepseek to X")
- ✅ Whisper garbles caught by difflib fuzzy matching at 0.72 cutoff
- ✅ Reasoning/ministral models load with 32768 context and minimum 2048 max_tokens

**End of Phase 3 (Latency):**
- STT < 1s (Whisper CUDA)
- First word spoken < 5s after STT completes (streaming TTS)
- Total latency < 20s for typical query
- Total latency < 30s for vision query

**Production Ready:**
- All Priority 1-5 items complete
- Security audit passed
- 48h+ uptime without crashes
