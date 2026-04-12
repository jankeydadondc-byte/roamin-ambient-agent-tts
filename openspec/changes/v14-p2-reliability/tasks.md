# Tasks: v14 P2 Reliability Remediation

> Execute in order — milestones are dependency-sorted.
> ⚠️ = Restart Roamin after this milestone.
> ✅ = Run test suite checkpoint.

---

## Milestone 1 — Model Config Cleanup (#14 #15 #16 #17)

- [ ] Open `agent/core/model_config.json`
- [ ] Remove entry `net-q4` (has `.pytest_tmp` path) — finding #14
- [ ] Remove entry `my-model-q4-k-m` (has `.pytest_tmp` path) — finding #14
- [ ] Remove Kimi-K2.5 shard entries 2–5 (keep only shard-1 entry) — finding #15
- [ ] Remove `mmproj_path` field from `ministral-3-14b-reasoning-2512-q4-k-m` — finding #16
- [ ] Change `context_window` for `qwen3-vl-8b-abliterated` from `8192` to `32768` — finding #17
- [ ] `python -c "import json; json.load(open('agent/core/model_config.json'))"` — valid JSON
- [ ] ✅ `pytest tests/test_model_router.py -v`
- [ ] ⚠️ Restart Roamin
- [ ] Commit: `fix(config): remove pytest artifacts, fix shard entries, mmproj, context_window (#14-17)`

---

## Milestone 2 — Memory DB Schema Hardening (#58 #59 #60)

- [ ] Read `agent/core/memory/memory_store.py` before editing
- [ ] Add `UNIQUE` constraint to `fact_name` column in `CREATE TABLE named_facts` — finding #58
- [ ] Change `add_named_fact()` INSERT to `INSERT OR REPLACE INTO named_facts` — finding #58
- [ ] Add `limit: int = 100` parameter to `get_conversation_history()`; add `LIMIT ?` to SQL — finding #59
- [ ] Update all call sites of `get_conversation_history()` that don't pass `limit` (confirm default is safe)
- [ ] Add `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` to `_connect()` or `__init__()` — finding #60
- [ ] `py_compile agent/core/memory/memory_store.py`
- [ ] ✅ `pytest tests/test_hitl_approval.py tests/test_memory_module.py -v`
- [ ] Commit: `fix(memory): UNIQUE named_facts, LIMIT history, WAL mode (#58 #59 #60)`

---

## Milestone 3 — ChromaDB Stability (#74 #75 #76)

- [ ] Read `agent/core/memory/memory_search.py` before editing
- [ ] Seed `_doc_counter` from `self._collection.count()` in `__init__()` — finding #74
- [ ] Add empty-collection guard before `collection.query()`: `n = min(n_results, self._collection.count())`, return empty dict if `n == 0` — finding #75
- [ ] Change production `PersistentClient` to `allow_reset=False` — finding #76
- [ ] `py_compile agent/core/memory/memory_search.py`
- [ ] ✅ `pytest tests/test_memory_module.py -v`
- [ ] Commit: `fix(memory): seed doc_counter, guard empty collection, disable allow_reset (#74 #75 #76)`

---

## Milestone 4 — chat_engine Pipeline Gaps (#22 #23 #25)

- [ ] Read `agent/core/chat_engine.py` before editing
- [ ] Add `_FACT_STOP_WORDS` set; add stop-word check in `extract_and_store_fact()` after pattern match — finding #22
- [ ] Add `session.add("user", message)` at start of `process_message()`, before fact extraction — finding #23
- [ ] Wrap `router.respond()` call in try/except; return user-readable fallback on exception — finding #25
- [ ] `py_compile agent/core/chat_engine.py`
- [ ] ✅ `pytest tests/test_chat_engine.py -v`
- [ ] Update `test_chat_engine.py` to cover: (a) stop-word blocks spurious fact, (b) router exception returns fallback string
- [ ] ✅ `pytest tests/test_chat_engine.py -v` — updated tests pass
- [ ] Commit: `fix(chat_engine): fact stop-words, session user turn, router exception fallback (#22 #23 #25)`

---

## Milestone 5 — Audit Log Atomic Write (#91)

- [ ] Read `agent/core/audit_log.py` before editing
- [ ] Replace `write_text()` in `_prune_if_needed()` with `tempfile.mkstemp()` + `os.replace()` pattern
- [ ] `py_compile agent/core/audit_log.py`
- [ ] Commit: `fix(audit): atomic prune with temp-then-replace to prevent log destruction (#91)`

---

## Milestone 6 — Model Sync Safety (#19 #20) ⚠️ RESTART REQUIRED

- [ ] Read `agent/core/model_sync.py` before editing
- [ ] Add `_SCAN_EXCLUSIONS` set with forbidden dir names — finding #19
- [ ] Replace bare `base.rglob("*.gguf")` calls with `_rglob_safe(base)` helper that skips excluded dirs — finding #19
- [ ] Add `_DRIVE_SCAN_TIMEOUT = 3.0` constant — finding #20
- [ ] Wrap `_drive_walk()` drive scans in `ThreadPoolExecutor` with `fut.result(timeout=_DRIVE_SCAN_TIMEOUT)` — finding #20
- [ ] `py_compile agent/core/model_sync.py`
- [ ] ⚠️ Restart Roamin
- [ ] Verify model sync log shows no scan into `roamin-ambient-agent-tts/` or forbidden dirs
- [ ] Commit: `fix(model_sync): exclude forbidden dirs from rglob, per-drive scan timeout (#19 #20)`

---

## Milestone 7 — Infrastructure Reliability (#90 #93 #96)

- [ ] Read `agent/core/roamin_logging.py`
- [ ] Fix `log_with_context()` — replace discarded `_` assignment with actual `logger_inst.log(level, formatted)` call — finding #90
- [ ] `py_compile agent/core/roamin_logging.py`

- [ ] Read `agent/core/resource_monitor.py`
- [ ] Add module-level `_cached_cpu` + background polling thread — finding #93
- [ ] Change `get_throttle_status()` to use cached value instead of blocking `cpu_percent(interval=0.5)` call
- [ ] `py_compile agent/core/resource_monitor.py`

- [ ] Edit `requirements.txt` — change `chromadb>=0.5.0` to `chromadb>=1.5.5` — finding #96
- [ ] `pip install -r requirements.txt --dry-run` — confirm version resolves to 1.x

- [ ] ✅ `pytest tests/test_control_api.py -v` (covers /health route indirectly)
- [ ] Commit: `fix(infra): fix log_with_context no-op, non-blocking CPU, pin chromadb>=1.5.5 (#90 #93 #96)`

---

## Milestone 8 — API & UI Wiring (#84 #85 #88)

- [ ] Read `ui/control-panel/src/App.jsx`
- [ ] Wire `setApiKey(storedKey)` call after key is loaded/entered — finding #84
- [ ] Read `ui/control-panel/src/apiClient.js`
- [ ] Change auth header from `Authorization: Bearer` to `x-roamin-api-key` — finding #85
- [ ] Add `discoverPort()` async function reading `.loom/control_api_port.json` with `8765` fallback — finding #85
- [ ] Replace hardcoded `127.0.0.1:8765` with dynamic port — finding #85

- [ ] Read `agent/control_api.py`
- [ ] Add `_TASK_EVICT_LIMIT = 500` constant — finding #88
- [ ] Add eviction logic to task registration: evict oldest half when limit exceeded — finding #88
- [ ] `py_compile agent/control_api.py`

- [ ] ✅ `pytest tests/test_control_api.py -v`
- [ ] ⚠️ Restart Roamin
- [ ] Manual test: open control panel, enter API key, send a chat message — verify auth header is sent correctly (browser devtools Network tab)
- [ ] Commit: `fix(api-ui): wire setApiKey, align auth header, port discovery, task eviction (#84 #85 #88)`

---

## Milestone 9 — Test Reliability (#103 #104)

- [ ] Read `tests/test_memory_module.py`
- [ ] Replace ephemeral in-memory ChromaDB fixture with `ChromaMemorySearch` pointed at `tmp_path` — finding #103
- [ ] Confirm existing tests still pass with production-path fixture
- [ ] Add test that calls `index_data()` twice on the same instance and asserts no `IDAlreadyExistsError` — finding #104
- [ ] ✅ `pytest tests/test_memory_module.py -v` — all pass, including new counter test
- [ ] Commit: `test(memory): use production ChromaDB fixture, add doc_counter collision test (#103 #104)`

---

## Final Validation

- [ ] ✅ Full v14 test suite:
  ```
  pytest tests/test_chat_engine.py tests/test_memory_module.py tests/test_hitl_approval.py tests/test_control_api.py tests/test_approval_gates.py tests/test_validators.py -v
  ```
- [ ] All tests green
- [ ] ⚠️ Final Roamin restart with all changes applied
- [ ] Verify `logs/wake_listener.log` shows no new errors after restart
- [ ] Update `openspec/changes/v14-p2-reliability/.openspec.yaml` → `status: complete`
- [ ] Commit: `chore: mark v14-p2-reliability complete`
