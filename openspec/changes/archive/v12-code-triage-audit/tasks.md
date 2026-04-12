# Tasks: v12 Code Triage Audit

## Setup
- [ ] Create `findings.md` in this directory before first triage session
- [ ] Confirm `anthropic-skills:code-triage-agent` skill is available

## Tier 1 — Entry Points & Core Loop
- [x] 01 `launch.py`
- [x] 02 `agent/core/agent_loop.py`
- [x] 03 `agent/core/config.py`
- [x] 04 `agent/core/paths.py`

## Tier 2 — Voice Pipeline
- [x] 05 `agent/core/voice/wake_listener.py`
- [x] 06 `agent/core/chat_engine.py`
- [x] 07 `agent/core/voice/stt.py`
- [x] 08 `agent/core/voice/tts.py`
- [x] 09 `agent/core/voice/session.py`
- [x] 10 `agent/core/voice/wake_word.py`

## Tier 3 — Inference & Model Layer
- [x] 11 `agent/core/model_router.py`
- [x] 12 `agent/core/llama_backend.py`
- [x] 13 `agent/core/model_sync.py`
- [x] 14 `agent/core/model_config.json`
- [x] 15 `agent/core/context_builder.py`
- [x] 16 `agent/core/system_prompt.txt`

## Tier 4 — Tool System
- [x] 17 `agent/core/tool_registry.py`
- [x] 18 `agent/core/tools.py`
- [x] 19 `agent/core/validators.py`
- [x] 20 `agent/core/audit_log.py`
- [x] 21 `agent/core/secrets.py`

## Tier 5 — Memory & Observation
- [x] 22 `agent/core/memory/memory_store.py`
- [x] 23 `agent/core/memory/memory_manager.py`
- [x] 24 `agent/core/memory/memory_search.py`
- [x] 25 `agent/core/observation.py`
- [x] 26 `agent/core/screen_observer.py`
- [x] 27 `agent/core/observation_scheduler.py`
- [x] 28 `agent/core/proactive.py`

## Tier 6 — Plugin System
- [x] 29 `agent/plugins/__init__.py`
- [x] 30 `agent/plugins/mempalace.py`

## Tier 7 — Control API & UI
- [x] 31 `agent/control_api.py`
- [x] 32 `ui/control-panel/src/App.jsx`
- [x] 33 `ui/control-panel/src/apiClient.js`
- [x] 34 `ui/control-panel/src/components/TaskHistory.jsx`
- [x] 35 `ui/control-panel/src/components/Sidebar.jsx`

## Tier 8 — Supporting Modules & Infrastructure
- [x] 36 `agent/core/roamin_logging.py`
- [x] 37 `agent/core/async_utils.py`
- [x] 38 `agent/core/resource_monitor.py`
- [x] 39 `agent/core/diagnostics.py`
- [x] 40 `agent/core/tray.py`
- [x] 41 `agent/core/ports.py`
- [x] 42 `requirements.txt`

## Tier 9 — Test Suite
- [x] 43 `tests/test_e2e_smoke.py`
- [x] 44 `tests/test_approval_gates.py`
- [x] 45 `tests/test_model_router.py`
- [x] 46 `tests/test_memory_module.py`
- [x] 47 `tests/test_control_api.py`
- [x] 48 Remaining test files

## Completion
- [x] All in-scope files have a `findings.md` entry
- [x] Remediation task list compiled at end of `findings.md`
- [x] Follow-up openspec created for any critical/high findings
