# Roamin Consolidated Priorities — Unified Roadmap

**Date:** 2026-04-01 (updated after resilience pass)
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

### Remaining Gaps

#### 1. Plugin-Level Fallback Chains
- If a plugin/tool has an alternative method, automatically try it
- Currently only direct dispatch → AgentLoop fallback exists
- No tool-to-tool fallback within AgentLoop itself
- **Files:** `agent/core/agent_loop.py`, `agent/core/tool_registry.py`

**Impact:** Priority 1 is now substantially complete. Remaining gaps are incremental improvements, not blockers.

---

## PRIORITY 2: VISION CAPABILITY COMPLETION

**Why second:** Your screen observer fires but can't actually show what's on screen. This is a core advertised feature that needs to work.

### Already Implemented
- ✅ Screen observation fires correctly via direct dispatch
- ✅ Screenshot saved to `workspace/screenshots/`
- ✅ Vision model (Ministral 3 14B + mmproj) registered in CAPABILITY_MAP
- ✅ **Default model upgraded to Qwen3-VL-8B abliterated (2026-04-01)**
  - Unified model: chat + vision + fast in one 4.7GB GGUF (Q4_K_M, uncensored)
  - Source: `prithivMLmods/Qwen3-VL-8B-Instruct-abliterated-v2-GGUF`
  - mmproj: Q8_0 (718MB) for multimodal projection
  - CAPABILITY_MAP routes default/chat/fast/vision/screen_reading to this model
  - _MMPROJ_MAP auto-resolves mmproj per model path (no hardcoded capability checks)
  - VRAM: 4.7GB model + 718MB mmproj vs old 14GB Qwen3 8B — frees ~9GB headroom

### Remaining Gap: Vision Routing (from "still needs work" #1)

#### 1. Screen Observation Vision Routing — PARTIALLY ADDRESSED
- **Previous state:** Default model (Qwen3 8B) had no vision — responded "I can't see images"
- **Current state:** Default model (Qwen3-VL-8B) has native vision capability
- **Remaining work:** Verify `take_screenshot()` passes image bytes correctly to llama_backend `chat()` with mmproj loaded. Direct dispatch pattern matching should now route vision queries to a capable model without special routing logic.
- **Test case:** ctrl+space → "what's on my screen" → should describe actual screen content
- **Status:** Pending manual end-to-end verification

#### 2. Feature Readiness Checks
- Pre-flight checks for vision dependencies (pyautogui, PIL, mmproj model loaded)
- Graceful degradation if certain features unavailable
- **Files:** `agent/core/screen_observer.py`, `agent/core/voice/wake_listener.py`

#### 3. Capability-Based Access Control
- Enable/disable features via configuration or user permissions
- Prevents "vision mode" from trying to process text-only queries incorrectly
- **Files:** `agent/core/agent_loop.py` (feature flag system)

**Impact:** Core advertised feature now has a capable model. Pending manual verification of end-to-end image processing pipeline.

---

## PRIORITY 3: PLUGIN SYSTEM FOUNDATION

**Why third:** Even if unused initially, this enables future extensibility without breaking stability.

### Planned Enhancements

#### 1. Plugin Isolation and Sandboxing
- Run plugins in isolated environments (venv containers or virtual threads with restricted access)
- Prevents one bad plugin from crashing the whole agent
- **Files:** `agent/core/plugin_loader.py` (new file)

#### 2. Graceful Task Termination for Plugins
- Ensures plugin cancellation properly releases resources
- Critical for long-running tool executions
- **Files:** `agent/core/agent_loop.py`, `agent/core/plugin_loader.py`

#### 3. Plugin Security Basics
- Restrict file operations in plugins to specific directories
- Prevents plugins from accessing sensitive system files
- **Files:** `agent/core/tool_registry.py`, `agent/core/plugin_loader.py`

#### 4. Structured Error Reporting for Plugins
- Plugin failures don't crash the agent, just emit errors
- **Files:** `agent/core/agent_loop.py`

**Impact:** Safe extensibility. Can add tools/plugins later without risking system stability.

---

## PRIORITY 4: ASYNC PERFORMANCE & RESOURCE MANAGEMENT

**Why fourth:** Once stable and functional, we optimize for responsiveness and prevent resource starvation.

### Remaining Latency Optimizations (from "still needs work")

#### 1. Streaming TTS (from "still needs work" #4)
- **Current:** Qwen3 generates full reply (~1.5s), THEN Chatterbox synthesizes (~12-22s)
- **Problem:** User hears silence during reply generation, then waits for TTS
- **Opportunity:** Biggest remaining latency win (~50% cut to perceived response time)
- **Solution:** Pipe model output sentence-by-sentence to Chatterbox as they complete
  - Requires rewriting `router.respond()` to yield tokens instead of returning full reply
  - **Note:** Chatterbox `/v1/audio/speech` likely does NOT support streaming (OpenAI-compat)
  - Alternative: sentence-level chunking — synthesize first sentence while generating rest
  - `model_router.respond()` currently returns `str`, both backends set `stream: False`
- **Complexity:** HIGH — refactor model output streaming + sentence splitting
- **Files:** `agent/core/model_router.py`, `agent/core/voice/tts.py`, `agent/core/voice/wake_listener.py`

#### 2. Whisper CUDA (from "still needs work" #5)
- **Current:** STT takes 5-6s on CPU (FP32)
- **Problem:** Accounts for ~25-30% of total response time
- **Options:**
  - A) Install CUDA torch (~3GB disk, ~500MB VRAM during STT)
  - B) Switch to whisper.cpp (C++ implementation, ~0.5s)
- **Impact:** Would cut STT to ~0.5s, total latency ~18-25s down to ~12-18s
- **Complexity:** MEDIUM — package swap
- **Files:** `agent/core/voice/stt.py`

#### 3. Asynchronous Task Execution
- Leverage Python's `asyncio` for non-blocking task execution
- I/O-bound operations: API calls, file operations, web searches
- Currently blocking calls can freeze the agent during web searches or large file reads
- **Files:** `agent/core/agent_loop.py`, `agent/core/tools.py`

#### 4. Background Task Cleanup
- Automatically clean up completed/timed-out tasks to avoid memory leaks
- Example: N.E.K.O's `_cleanup_task_registry()` and `_cleanup_of_bg()`
- **Files:** `agent/core/agent_loop.py`

#### 5. Resource Monitoring and Throttling (from "still needs work" #7 - TurboQuant)
- Monitor CPU/memory/GPU usage
- Implement throttling for high-frequency tasks (API rate limits)
- **TurboQuant KV cache compression** (deferred):
  - Would free ~1-4GB VRAM during inference
  - Requires migrating from llama-cpp-python to HuggingFace or vLLM
  - Package status: 0.2.0 alpha (released 2026-03-27) — evaluate next quarter
- **Files:** `agent/core/llama_backend.py`, `agent/core/model_router.py`

#### 6. Model Selection — Voice Control (from "still needs work" #2)
- **Current state:** Hardcoded in CAPABILITY_MAP, auto-selected by keyword
- **Problem:** No voice-controlled way to pick model (Ministral 14B for complex tasks)
- **Options:**
  - A) Voice trigger words ("use ministral", "think hard")
  - B) Memory preference ("my preferred reasoning model is ministral")
  - C) Query prefix ("ministral: what's on my screen")
- **Note:** Ministral 14B capabilities registered but nothing routes to them yet
- **Complexity:** LOW-MEDIUM — add routing rules
- **Files:** `agent/core/model_router.py`, `agent/core/voice/wake_listener.py`

**Impact:** Reduced latency, prevents resource exhaustion, smoother operation. Perceived response time cut to ~12-18s.

---

## PRIORITY 5: TASK EXECUTION ROBUSTNESS

**Why fifth:** Once stable and functional with vision working, handle task scheduling intelligently.

### Planned Enhancements

#### 1. Task Deduplication
- Prevent redundant task execution if same instruction queued multiple times
- Double-launch is fixed at VBS level, but AgentLoop itself has no dedup
- **Files:** `agent/core/agent_loop.py`

#### 2. Dynamic Task Prioritization
- Priority-based queue system (high/medium/low)
- Can assign based on urgency or user input
- **Files:** `agent/core/agent_loop.py`

**Impact:** More reliable multi-task handling, prevents spamming agent with same request.

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
- Critical for debugging complex workflows
- **Files:** `agent/core/memory/memory_manager.py`

#### 4. RoaminCP UI Integration (from "still needs work" #6)
- **Current state:** RoaminCP UI exists (Tauri + React, Monaco editor, xterm terminal, diff viewer)
  - Location: `C:\AI\os_agent\ui\roamin-control`
  - Not yet connected to ambient agent
  - Control API still points at os_agent, not new repo
- **Solution:** Wire RoaminCP to this repo's Control API, add websocket event streaming
- **Complexity:** MEDIUM-HIGH — cross-repo integration
- **Timeline:** After vision routing + streaming TTS complete
- **Files:** `agent/core/api.py` (new), wiring to RoaminCP

**Impact:** Better user feedback, easier troubleshooting, more transparent operation.

---

## PRIORITY 7: SECURITY & INTEGRATION HARDENING

**Why seventh:** Once everything else works well, harden the perimeter and prepare for production deployment.

### Planned Enhancements

#### 1. API Key Management
- Secure management of credentials via environment variables/secrets manager
- Currently avoid hardcoded values but no central system
- **Files:** `agent/core/config.py`

#### 2. LLM Proxy Layer
- Normalize responses from different LLM providers
- Current model routing is internal, not provider-agnostic
- **Files:** `agent/core/model_router.py` (refactor)

#### 3. Browser Automation
- Integrate Selenium/Playwright for web interactions
- Currently only have `web_search`, no browser control
- **Files:** `agent/core/tools.py` (new browser tools)

**Impact:** Production-ready security and broader capability set.

---

## EXECUTION ROADMAP (by phase)

### Phase 1: Stabilization (COMPLETE ✅)
- ✅ Fix 5 critical bugs (Stabilization Pass — 2026-03-31)
- ✅ Test end-to-end voice flow
- ✅ Verify direct dispatch + AgentLoop both functional

### Phase 1.5: Resilience (COMPLETE ✅)
- ✅ Double-launch VBS fix
- ✅ AgentLoop cancellation + 30s tool timeouts
- ✅ HTTP retry with exponential backoff
- ✅ Direct dispatch fallback to AgentLoop
- ✅ Input validation + structured error categories
- ✅ Log prune 40KB limit
- ✅ Manual test passed: 4 wakes, all successful, thread guard confirmed

### Phase 2: Vision (IN PROGRESS)
**Estimated:** 1-2 days
**Items:** Priority 2 (vision routing)
- ✅ Downloaded Qwen3-VL-8B abliterated (Q4_K_M, 4.7GB) + mmproj (Q8_0, 718MB)
- ✅ Updated CAPABILITY_MAP: default/chat/fast/vision/screen_reading → Qwen3-VL-8B
- ✅ Added _MMPROJ_MAP for auto-resolving mmproj per model path
- ✅ Updated model_config.json routing rules + fallback chain
- ✅ Unit tests passed (CAPABILITY_MAP routing, file existence, mmproj lookup)
- ⬜ Manual test: ctrl+space → "what's on my screen" → actual description
- ⬜ Verify image bytes pipeline (take_screenshot → llama_backend.chat with mmproj)

### Phase 3: Task Scheduling (AFTER VISION)
**Estimated:** 1-2 days
**Items:** Priority 5 (task handling)
1. Task deduplication + prioritization (agent_loop.py)

### Phase 4: Latency Optimization (PARALLEL)
**Estimated:** 3-5 days
**Items:** Priority 4 (async, streaming, CUDA)
1. Streaming TTS (model_router.py → yield tokens, tts.py → consume stream)
2. Whisper CUDA (stt.py — package swap)
3. Model selection voice control (model_router.py + wake_listener.py)
4. Async task execution (agent_loop.py, tools.py)

### Phase 5: UX & Extensibility (ASYNC)
**Estimated:** 4-6 days
**Items:** Priority 3 (plugins) + Priority 6 (UX)
1. Plugin isolation & sandboxing (plugin_loader.py new)
2. Task history & notifications (memory_manager.py + tts.py)
3. RoaminCP UI integration (control_api.py new)

### Phase 6: Security Hardening (FINAL)
**Estimated:** 2-3 days
**Items:** Priority 7 (security)
1. API key management (config.py new)
2. LLM proxy layer (model_router.py refactor)
3. Browser automation tools (tools.py extend)

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
- Screen observation vision routing → MODEL UPGRADED, pending manual e2e test

### High (Improve Reliability)
- Task deduplication
- Plugin-level fallback chains

### Medium (Latency & UX)
- Streaming TTS
- Whisper CUDA
- Model selection voice control
- Task progress updates

### Low (Nice-to-Have)
- Plugin system
- RoaminCP UI integration
- TurboQuant KV cache

---

## Success Criteria

**End of Phase 1.5 (Resilience): ✅ ACHIEVED**
- No hangs > 30s (tool timeouts fire) ✅
- API errors retry exponentially (2x with 1s, 2s backoff) ✅
- Invalid inputs rejected gracefully (URL scheme, size limits, control chars) ✅
- Failed direct dispatch falls through to AgentLoop ✅
- Rapid ctrl+space drops duplicate presses ✅

**End of Phase 2 (Vision):**
- ctrl+space → "what's on my screen" returns actual screen description
- No false "can't see images" responses
- llama_backend.chat() handles image bytes with vision model + mmproj

**End of Phase 4 (Latency):**
- Streaming TTS perceivable (reply starts during final LLM tokens)
- STT < 1s (CUDA enabled)
- Total latency < 20s for typical query

**Production Ready:**
- All Priority 1-5 items complete
- Security audit passed
- 48h+ uptime without crashes
