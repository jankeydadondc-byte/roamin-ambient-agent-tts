Prioritized Improvement Batch

Here's my logical priority order for reaching a stable solid ambient agent base:

✅ COMPLETED: THINK TOKEN STREAMING + REPLY QUALITY (2026-04-04)

Session fixed think-tier queries end-to-end:

1. **AgentLoop bypass for think queries** — Think-tier queries (LOW/MED/HIGH) now bypass AgentLoop entirely. Previously, queries like "think really hard about X" would enter AgentLoop, attempt grep/web_search tools that timeout, and hang Roamin for 30s+. Now a precheck runs `_classify_think_level()` before AgentLoop, and if active, routes straight to LLM.

2. **Think routing to DeepSeek R1** — Default model (Qwen3-VL-8B) never generates `<think>` tags. When `stream_think=True`, task_type is automatically overridden to `"reasoning"` (DeepSeek R1 8B) which reliably produces `<think>...</think>` chains.

3. **Force `<think>` prefix in ChatML prompt** — `_format_chatml()` now appends `<think>\n` when `no_think=False`, guaranteeing the model enters think mode. `_stream_with_think_print()` detects the prefilled tag and starts streaming immediately — no silent inference.

4. **Think-tier system prompt** — Previously all queries got "Reply in ONE short sentence." Think-tier queries now get "Give a thorough, detailed response. You may use multiple sentences." This allows comprehensive answers without forcing brevity.

5. **Removed 200-char truncation for think replies** — `reply[:200]` only applies to OFF-tier (no_think=True) queries. Think-tier gets full model output, spoken sentence-by-sentence via streaming TTS.

6. **Hyphenated "deep-seek" model override** — Whisper sometimes transcribes "deepseek" as "deep-seek". Added 4 hyphenated variants to `_EXACT_PREFIXES` so model override correctly strips the phrase and routes cleanly.

7. **Trailing partial tag strip** — Added `re.sub(r"</?[\w]*>?\s*$", "", reply)` to strip `</s>`, `</`, or other partial closing tags that survive the 200-char truncation edge.

**Verified working:** "think really hard about color theory" → cyan think stream → 1000+ char comprehensive reply, fully spoken, zero truncation. 62/62 tests passing.

✅ COMPLETED: PHASE 3B STREAMING TTS + VRAM MANAGEMENT + MODEL AUTO-SYNC (2026-04-04)

VSCode session completed three major features:

1. **Streaming TTS (Phase 3B)** — sentence-chunked synthesis with prefetch-1 pipeline
   - tts.py: _split_sentences() with abbreviation masking + ellipsis handling
   - speak_streaming() tokenizes reply → splits by sentence → prefetch-1 ThreadPoolExecutor
   - Chatterbox synthesis per-sentence with 2 retries + timeout formula min(15 + len//10, 33)
   - Fallback: if Chatterbox unavailable, per-sentence pyttsx3 fallback
   - Synthesis failure on sentence N no longer aborts remaining sentences
   - Tests: 4 test classes (62+ tests), all passing

2. **VRAM Management** — LLM unload before TTS synthesis
   - llama_backend.py: unload_current_model() exported function to free VRAM
   - wake_listener.py: _unload_llm() called between reply generation and TTS
   - Frees ~5.4GB for Chatterbox CUDA synthesis, reloads on next inference
   - Threading: RLock (reentrant) prevents deadlock in nested lock scenarios

3. **Capability-Aware Model Routing (Model Auto-Sync)**
   - model_router.py: best_task_for(capability) method routes vision/code/reasoning queries
   - llama_backend.py: _VISION_CAPABILITIES frozenset gates mmproj loading
   - mmproj only loads when vision capability in query (saves VRAM, prevents stalls)
   - Cache gates on model_path AND mmproj_path (no collision)
   - model_sync.py: walks filesystems + Ollama blobs, idempotently syncs model_config.json

First run registered 6 additional models from LM Studio dirs. Roamin no longer requires external servers.

All systems integrated and tested: 62/62 tests passing, Roamin stable, zero errors in logs.

✅ COMPLETED: STANDALONE MODEL DISCOVERY (2026-04-03)

Roamin no longer requires LM Studio or Ollama to be running. At startup, model_sync.py:

- Walks all drive letters looking for `models/` directories (depth-limited, skips system dirs)
- Scans ~/.lmstudio/models/ recursively for .gguf files
- Resolves Ollama blob sha256 files to friendly name:tag via manifest JSON parsing
- Auto-detects paired mmproj files for vision models
- Idempotently appends net-new entries to model_config.json (0 re-adds on repeat runs)
- model_router.py dispatches config entries with file_path directly to LlamaCppBackend

OpenSpec change: standalone-filesystem-model-discovery (25/25 tasks complete)

PRIORITY 1: CORE STABILITY \& ERROR RESILIENCE

Why first: Without these, the agent can crash or hang unpredictably. Stability is the foundation.

Includes:

Graceful Task Termination (from section 1)

Implement proper cleanup when tasks are cancelled

Critical for computer-use/browser-use operations

Task Timeout and Retry Logic (from section 1)

Add configurable timeouts to prevent indefinite hangs

Implement exponential backoff for transient failures (API rate limits, network issues)

Directly addresses the double-launch issue and Chatterbox 500 errors

Fallback Mechanisms (from section 4)

If a plugin fails, switch to alternative method or notify user

Currently your direct dispatch has no fallback → brittle

Structured Error Reporting (from section 4)

Standardize error messages across the agent

Currently errors are scattered in logs without clear pattern

Input Validation (from section 8)

Validate all user inputs to prevent injection attacks

Critical for clipboard\_read, open\_url, web\_search tools

Impact: Prevents crashes, hangs, and data corruption. Makes the agent production-ready.

PRIORITY 2: VISION CAPABILITY COMPLETION

Why second: Your screen observer fires but can't actually show me what's on screen. This is a core advertised feature that needs to work.

Includes:

Screen Observation Vision Routing (Critical Gap #1)

Detect when screenshot result exists

Route to vision/ministral\_vision capability with actual image bytes

Currently passes text to default model → "can't see images" bug

Feature Readiness Checks (from section 3)

Pre-flight checks for vision dependencies (pyautogui, PIL, mmproj model loaded)

Graceful degradation if certain features unavailable

Capability-Based Access Control (from section 3)

Enable/disable features via configuration or user permissions

Prevents "vision mode" from trying to process text-only queries incorrectly

Impact: Core advertised feature works. User can ask "what am I looking at?" and get actual description.

PRIORITY 3: PLUGIN SYSTEM FOUNDATION

Why third: Even if unused initially, this enables future extensibility without breaking stability.

Includes:

Plugin Isolation and Sandboxing (from section 2)

Run plugins in isolated environments (venv containers or virtual threads with restricted access)

Prevents one bad plugin from crashing the whole agent

Graceful Task Termination for Plugins (combines Priority 1 + 2)

Ensures plugin cancellation properly releases resources

Critical for long-running tool executions

Plugin Security Basics (from section 8)

Restrict file operations in plugins to specific directories

Prevents plugins from accessing sensitive system files

Structured Error Reporting for Plugins (combines with Priority 1)

Plugin failures don't crash the agent, just emit errors

Impact: Safe extensibility. Can add tools/plugins later without risking system stability.

PRIORITY 4: ASYNC PERFORMANCE \& RESOURCE MANAGEMENT

Why fourth: Once stable and functional, we optimize for responsiveness.

Includes:

Asynchronous Task Execution (from section 5)

Leverage asyncio for I/O-bound operations (API calls, file ops)

Currently blocking calls can freeze the agent during web searches or large file reads

Background Task Cleanup (from section 5)

Automatically clean up completed/timed-out tasks to avoid memory leaks

Example: N.E.K.O's \_cleanup\_task\_registry() and \_cleanup\_of\_bg()

Resource Monitoring and Throttling (from section 5)

Monitor CPU/memory/GPU usage

Implement throttling for high-frequency tasks (API rate limits)

Impact: Reduced latency, prevents resource exhaustion, smoother operation.

PRIORITY 5: TASK EXECUTION ROBUSTNESS

Why fifth: Once stable and functional with vision working, handle task scheduling intelligently.

Includes:

Task Deduplication (from section 1)

Prevent redundant task execution if same instruction queued multiple times

Directly helps with double-launch issue

Dynamic Task Prioritization (from section 1)

Priority-based queue system (high/medium/low)

Can assign based on urgency or user input

Impact: More reliable multi-task handling, prevents spamming agent with same request.

PRIORITY 6: USER EXPERIENCE ENHANCEMENTS

Why sixth: After stability and core features work, improve the experience.

Includes:

Real-Time Task Progress Updates (from section 6)

Forward progress updates for long-running tasks

Current web search gives no indication it's working

Notification System (from section 6)

Toast notifications for task completion/failures/events

Currently rely solely on TTS replies

Task History and Logging (from section 6)

Maintain history of executed tasks with timestamps, results

Critical for debugging complex workflows

Impact: Better user feedback, easier troubleshooting, more transparent operation.

PRIORITY 7: SECURITY \& INTEGRATION HARDENING

Why seventh: Once everything else works well, harden the perimeter and prepare for production deployment.

Includes:

API Key Management (from section 8)

Secure management of credentials via environment variables/secrets manager

Currently avoid hardcoded values but no central system

LLM Proxy Layer (from section 7)

Normalize responses from different LLM providers

Current model routing is internal, not provider-agnostic

Browser Automation (from section 7)

Integrate Selenium/Playwright for web interactions

Currently only have web\_search, no browser control

Impact: Production-ready security and broader capability set.

Implementation Strategy

For each priority batch:

Read relevant source files in the correct repo paths (agent/core/\*)

Create minimal surgical edits — don't rewrite entire files

Use py\_compile\_check after writing any Python file

Run flake8 --max-line-length=120 before commit

Verify changes work with simple test queries

Check logs for new errors
