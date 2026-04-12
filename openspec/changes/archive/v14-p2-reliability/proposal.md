# v14 P2 Reliability Remediation — Proposal

## Goal

Fix the remaining 25 P2 findings from the v12 code triage audit. These are not
security emergencies (those shipped in v13) but they represent real correctness
bugs, crash conditions, and silent failures that degrade Roamin's daily behaviour.

Findings are grouped into 9 milestones ordered by dependency and impact.

---

## Milestone 1 — Model Config Cleanup (#14 #15 #16 #17)

**File:** `agent/core/model_config.json`

The config has accumulated four categories of corruption from testing and
copy-paste. None require code changes — JSON edits only.

| # | What | Fix |
|---|------|-----|
| #14 | Two entries with `.pytest_tmp` paths (`net-q4`, `my-model-q4-k-m`) | Remove both entries entirely |
| #15 | Five Kimi-K2.5 shard files (shards 2–5) registered as standalone models | Remove shards 2–5; retain only shard-1 which is the entry point |
| #16 | `ministral-3-14b-reasoning` has `mmproj_path` (text-only model) | Remove the `mmproj_path` field from that entry |
| #17 | `qwen3-vl-8b-abliterated` (primary model) has `context_window: 8192` | Change to `32768` to match all other entries |

**Verification:** `py_compile` not needed (JSON). Run `python -c "import json; json.load(open('agent/core/model_config.json'))"` to confirm valid JSON. Run existing model router tests.

⚠️ **Restart required** — ModelRouter caches the config at import time.

---

## Milestone 2 — Memory DB Schema Hardening (#58 #59 #60)

**File:** `agent/core/memory/memory_store.py`

Three SQLite reliability issues that cause silent data corruption and lock
contention on a busy agent.

### #58 — `named_facts` UNIQUE constraint

**Problem:** `add_named_fact()` always `INSERT`s. Calling `get_named_fact()` returns the first (oldest, stale) row. Facts accumulate silently.

**Fix:**
```sql
-- In CREATE TABLE named_facts:
fact_name TEXT NOT NULL UNIQUE,
-- Change INSERT to INSERT OR REPLACE (upsert semantics)
```

Update `add_named_fact()` to use `INSERT OR REPLACE INTO named_facts`.
Update `get_all_named_facts()` to `SELECT DISTINCT ON fact_name` (or rely on UNIQUE to guarantee uniqueness after migration).

### #59 — `get_conversation_history()` unbounded SELECT

**Problem:** `SELECT *` with no LIMIT on every context build. Large history → large memory read on every message.

**Fix:** Add `LIMIT` parameter with default `100`:
```python
def get_conversation_history(self, limit: int = 100) -> list[dict]:
    ...
    cursor.execute(
        "SELECT role, content FROM conversation_history ORDER BY id DESC LIMIT ?",
        (limit,),
    )
```

### #60 — No WAL mode

**Problem:** Without WAL, concurrent readers block writers and vice versa. The wake listener and control API both write to the same DB.

**Fix:** Add to `_connect()` or `__init__()`:
```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
```

**Verification:** `pytest tests/test_hitl_approval.py tests/test_memory_module.py -v`

---

## Milestone 3 — ChromaDB Stability (#74 #75 #76)

**File:** `agent/core/memory/memory_search.py`

Three bugs that cause the memory search layer to crash or corrupt data silently.

### #74 — `_doc_counter` ID collision

**Problem:** `_doc_counter = 0` is an instance attribute. Every `ChromaMemorySearch()` construction resets it to 0. After the first session, `index_data()` generates `doc_0`, `doc_1`... → `IDAlreadyExistsError` in ChromaDB.

**Fix:** Seed from current collection count at construction time:
```python
def __init__(self, ...):
    ...
    existing = self._collection.count()
    self._doc_counter = existing  # continue from where we left off
```

### #75 — Empty collection crash

**Problem:** `collection.query(n_results=5)` raises `InvalidArgumentError` when collection has 0 documents (`n_results > collection.count()`).

**Fix:** Guard with min():
```python
n = min(n_results, self._collection.count())
if n == 0:
    return {"documents": [], "metadatas": [], "distances": []}
results = self._collection.query(..., n_results=n)
```

### #76 — `allow_reset=True` in production

**Problem:** The production `PersistentClient` is constructed with `allow_reset=True`, which enables `client.reset()` — a destructive operation that wipes the entire collection.

**Fix:** Change to `allow_reset=False` for the production path. Only the test fixture should use `allow_reset=True`.

**Verification:** `pytest tests/test_memory_module.py -v`

---

## Milestone 4 — chat_engine Pipeline Gaps (#22 #23 #25)

**File:** `agent/core/chat_engine.py`

Three correctness bugs in the unified message pipeline that degrade chat quality.

### #22 — `_FACT_PATTERNS[1]` too broad

**Problem:** `r"my (.+?) is (.+)"` has no leading verb anchor. "my code is broken", "my screen is black" all store as named facts.

**Fix:** Tighten pattern to require an intent verb prefix, or add a stop-word denylist for common complaint/status nouns:
```python
_FACT_STOP_WORDS = {
    "code", "screen", "internet", "wifi", "computer", "laptop",
    "phone", "mouse", "keyboard", "connection", "network", "battery",
    "head", "back", "stomach", "foot", "hand", "eye",
}

# In extract_and_store_fact(), after matching pattern #1 (index 1):
if fact_name.split()[0] in _FACT_STOP_WORDS:
    continue  # Skip — this is a complaint, not a biographical fact
```

### #23 — Missing `session.add("user", message)`

**Problem:** `process_message()` adds the assistant reply to session but never adds the user message. The context block the model sees is always one turn behind.

**Fix:** Add at the top of `process_message()`, before fact extraction:
```python
session.add("user", message)
```

### #25 — `router.respond()` uncaught exception

**Problem:** Model unreachability raises an unhandled exception that propagates as HTTP 500.

**Fix:** Wrap in try/except:
```python
try:
    reply = router.respond(...)
except Exception as exc:
    logger.error("[chat_engine] ModelRouter failed: %s", exc)
    reply = "I can't reach my model right now. Is LM Studio running?"
```

**Verification:** `pytest tests/test_chat_engine.py -v` — update fallback tests to cover the new exception path.

---

## Milestone 5 — Audit Log Atomic Write (#91)

**File:** `agent/core/audit_log.py`

**Problem:** `_prune_if_needed()` uses `write_text()` directly. A crash or power loss mid-write destroys the entire audit log.

**Fix:** Write to a temp file then `os.replace()`:
```python
import tempfile, os

# In _prune_if_needed():
tmp_fd, tmp_path = tempfile.mkstemp(dir=LOG_PATH.parent, suffix=".tmp")
try:
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
        f.write(pruned_content)
    os.replace(tmp_path, LOG_PATH)
except Exception:
    os.unlink(tmp_path)
    raise
```

**Verification:** `py_compile agent/core/audit_log.py` — no existing unit test for this; verify manually or add a test.

---

## Milestone 6 — Model Sync Safety (#19 #20)

**File:** `agent/core/model_sync.py`

### #19 — `rglob` into forbidden directories

**Problem:** `_WELL_KNOWN_SCAN_DIRS` includes `Path("C:/AI")`, causing `rglob("*.gguf")` to recurse into `C:/AI/roamin-ambient-agent-tts/.venv`, `N.E.K.O.`, `framework`, etc. Sex-roleplay model entries appear in production config as a direct result.

**Fix:**
```python
_SCAN_EXCLUSIONS = {
    "roamin-ambient-agent-tts",
    ".venv",
    ".venv_external",
    "N.E.K.O.",
    "framework",
    "node_modules",
}

def _rglob_safe(base: Path) -> list[Path]:
    """rglob *.gguf, skipping excluded subdirectories."""
    results = []
    for p in base.rglob("*.gguf"):
        if not any(excl in p.parts for excl in _SCAN_EXCLUSIONS):
            results.append(p)
    return results
```

Replace bare `base.rglob("*.gguf")` calls with `_rglob_safe(base)`.

### #20 — `_drive_walk()` no timeout

**Problem:** Scanning all A–Z drives with no timeout blocks startup on systems with network drives or removable media.

**Fix:** Add per-drive timeout using `concurrent.futures`:
```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

_DRIVE_SCAN_TIMEOUT = 3.0  # seconds per drive

def _drive_walk() -> list[Path]:
    found = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_scan_drive, letter): letter for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
        for fut, letter in futures.items():
            try:
                found.extend(fut.result(timeout=_DRIVE_SCAN_TIMEOUT))
            except (FuturesTimeout, Exception):
                logger.debug("[model_sync] Drive %s: scan skipped (timeout or error)", letter)
    return found
```

**Verification:** `py_compile agent/core/model_sync.py`

⚠️ **Restart required** — model sync runs at startup.

---

## Milestone 7 — Infrastructure Reliability (#90 #93 #96)

### #90 — `log_with_context()` silent discard

**File:** `agent/core/roamin_logging.py`

**Problem:** `log_with_context()` formats a message into `_` and never calls the logger. Diagnostic logging is a no-op.

**Fix:** Call the underlying logger:
```python
def log_with_context(logger_inst, level, message, **context):
    formatted = f"{message} | {context}" if context else message
    logger_inst.log(level, formatted)  # was: _ = f"{message} | {context}"
```

### #93 — `get_throttle_status()` blocks event loop

**File:** `agent/core/resource_monitor.py`

**Problem:** `psutil.cpu_percent(interval=0.5)` is called twice per `/health` request, blocking the async event loop for 1.0–5.5s.

**Fix:** Use a background-cached reading:
```python
_cached_cpu: float = 0.0
_cpu_lock = threading.Lock()

def _update_cpu_cache():
    global _cached_cpu
    with _cpu_lock:
        _cached_cpu = psutil.cpu_percent(interval=1.0)

# Start background updater thread at module init:
threading.Thread(target=_poll_cpu_loop, daemon=True).start()

def get_throttle_status() -> dict:
    # Use cached value — never blocks
    cpu = _cached_cpu
    ...
```

### #96 — `chromadb>=0.5.0` allows broken 0.6.x

**File:** `requirements.txt`

**Problem:** `chromadb>=0.5.0` allows versions 0.6.x which have known breaking API changes. The project is tested against 1.x.

**Fix:**
```
chromadb>=1.5.5
```

**Verification:** `pip install -r requirements.txt --dry-run` confirms version resolution. `pytest tests/test_memory_module.py -v`.

---

## Milestone 8 — API & UI Wiring (#84 #85 #88)

### #84 — `setApiKey()` never called in UI

**File:** `ui/control-panel/src/App.jsx`

**Problem:** `API_KEY` in `apiClient.js` is always `null`. The auth key input is present in the UI but never actually wired through to the API client.

**Fix:** After the user sets the key (wherever it's stored/loaded), call `setApiKey(key)` from the imported apiClient:
```jsx
import { setApiKey } from './apiClient';
// When key is loaded from localStorage or entered:
setApiKey(storedKey);
```

### #85 — Auth header mismatch + hardcoded port

**File:** `ui/control-panel/src/apiClient.js`

**Problem (a):** UI sends `Authorization: Bearer <key>`, backend middleware checks `x-roamin-api-key`. Auth never succeeds.

**Fix:** Change the header in `apiClient.js`:
```js
headers: { 'x-roamin-api-key': API_KEY }
```

**Problem (b):** Port discovery reads hardcoded `127.0.0.1:8765` instead of `.loom/control_api_port.json`.

**Fix:** Read port from the `.loom` file at startup:
```js
async function discoverPort() {
    try {
        const r = await fetch('/.loom/control_api_port.json');
        const { port } = await r.json();
        return port;
    } catch {
        return 8765; // fallback
    }
}
```

### #88 — `app.state.tasks` grows unbounded

**File:** `agent/control_api.py`

**Problem:** The background task dict is never evicted. Long-running Roamin instances accumulate thousands of stale entries.

**Fix:** Cap at 500 most recent entries on every insert:
```python
_TASK_EVICT_LIMIT = 500

def _register_task(task_id: str, info: dict) -> None:
    app.state.tasks[task_id] = info
    if len(app.state.tasks) > _TASK_EVICT_LIMIT:
        # Evict oldest half
        oldest = sorted(app.state.tasks)[:_TASK_EVICT_LIMIT // 2]
        for k in oldest:
            del app.state.tasks[k]
```

**Verification:** `pytest tests/test_control_api.py -v`

---

## Milestone 9 — Test Reliability (#103 #104)

### #103 — ChromaDB fixture masks production crash

**File:** `tests/test_memory_module.py`

**Problem:** The test fixture uses an ephemeral in-memory ChromaDB client that never raises on empty collection. The production crash from finding #75 is completely invisible in tests.

**Fix:** Replace the test fixture with `ChromaMemorySearch` pointed at a real temp directory:
```python
@pytest.fixture
def chroma_search(tmp_path):
    from agent.core.memory.memory_search import ChromaMemorySearch
    return ChromaMemorySearch(persist_directory=str(tmp_path / "chroma_test"))
```

### #104 — `_doc_counter` collision not tested

**File:** `tests/test_memory_module.py`

**Problem:** Finding #74 (ID collision on re-instantiation) is never triggered by tests.

**Fix:** Add a test that calls `index_data()` twice with the same data on the same production `ChromaMemorySearch` instance and asserts no `IDAlreadyExistsError`.

**Verification:** `pytest tests/test_memory_module.py -v`

---

## Deferred

**#24** — AgentLoop `on_progress` callback for chat overlay. Requires wiring a
WebSocket broadcast from `process_message()` through the Control API. Scope
exceeds a single milestone; tracked separately.

---

## Rollback Strategy

```
git revert <commit-hash>
```

All milestones are independent commits. Any single milestone can be reverted
without affecting others. Model config changes can be manually reverted from the
JSON; DB schema changes (`ALTER TABLE` / `PRAGMA`) do not require migration
rollback for SQLite (WAL mode is backwards-compatible; UNIQUE constraint will
fail on duplicate inserts, surfacing latent bugs rather than hiding them).

---

## Post-Remediation State

| Area | Before | After |
|---|---|---|
| Named facts | Stale duplicates accumulate; complaints stored as facts | Upsert semantics; stop-word filter; deduplicated |
| Conversation context | Current user turn invisible to model | User turn added before LLM call |
| Model crashes | `router.respond()` raises HTTP 500 | Graceful fallback message |
| ChromaDB empty collection | Raises `InvalidArgumentError` on fresh install | Guarded; returns empty results |
| ChromaDB ID collision | `IDAlreadyExistsError` on re-instantiation | Counter seeded from collection size |
| ChromaDB allow_reset | Destructive reset enabled in production | Disabled for production client |
| SQLite concurrent writes | `database is locked` errors under load | WAL mode enabled |
| Audit log crash | Write failure destroys log | Atomic temp-then-replace |
| Model config | pytest artifacts, broken shards, wrong context window | Cleaned; accurate metadata |
| Model scan | Recurses into forbidden dirs; scans all drives at startup | Exclusion list; per-drive timeout |
| API auth UI | Auth header never sent; port hardcoded | Header aligned; port discovered |
| Task dict | Grows unbounded | Capped at 500 with LRU eviction |
| Logging | `log_with_context()` is a no-op | Calls underlying logger |
| /health latency | Blocks event loop 1–5s | Background-cached CPU reading |
| chromadb version | Allows broken 0.6.x | Pinned to >=1.5.5 |
