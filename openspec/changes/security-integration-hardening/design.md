# Design: Security & Integration Hardening

## Design Decisions

### D1: Allowlist over denylist for path validation

**Decision:** Validate paths against an allowlist of safe root directories, not a denylist
of dangerous ones.

**Why:** Denylists always miss something (`C:\Windows` but not `\\?\C:\Windows`, symlinks
into system dirs, UNC paths). An allowlist is simpler and fails closed -- unknown paths are
rejected by default.

**Allowlist (configurable):**
- Project root: `C:\AI\roamin-ambient-agent-tts\`
- User home: `C:\Users\Asherre Roamin\`
- Temp dirs: `%TEMP%`, `.pytest_tmp/`

Write/delete operations get a stricter subset (project root + temp only).
Read operations get the full allowlist.

### D2: JSONL audit log over SQLite

**Decision:** Use append-only `.jsonl` file (`logs/audit.jsonl`) instead of a SQLite table.

**Why:**
- Append-only writes never corrupt on crash (no transactions needed)
- Human-readable with `cat` or `jq` -- no tooling required
- Auto-prunable with the same `_prune_log()` pattern used for `wake_listener.log`
- No schema migrations, no DB connections, no locking
- Query endpoint does a simple reverse-read with optional filters

SQLite is overkill for write-once-read-rarely audit data in a single-user local tool.

### D3: Wire existing HITL approval mechanism, don't build new

**Decision:** Reuse the `pending_approvals` table + toast notification flow from Priority 6
for high-risk tool approval. No new approval UI.

**Why:** The approval mechanism already exists (commit af9b59c):
- `pending_approvals` SQLite table in `memory_store.py`
- `_notify_approval_toast()` fires winotify toast with Approve/Deny buttons
- `/approve` and `/deny` Control API endpoints
- `wake_listener._handle_blocked_steps()` polls for approval

The only new work is wiring `tool_registry.execute()` to check risk level and route
high-risk tools through this flow instead of executing immediately.

### D4: Secrets module wraps python-dotenv, not keyring

**Decision:** Use `python-dotenv` for `.env` file loading, not `keyring` or Windows
Credential Manager.

**Why:**
- `keyring` requires platform-specific backends and GUI prompts on some systems
- `.env` files are the universal standard for local dev secrets
- Already in `.gitignore` (`*.env` patterns should be added)
- `python-dotenv` is pure Python, zero native deps, 1 file
- Future upgrade path: swap `get_secret()` internals to keyring without changing callers

### D5: Response size limit at HTTP layer, not model layer

**Decision:** Cap response body size in `model_router.py` HTTP fallback path at 256KB.

**Why:**
- llama-cpp-python (local) responses are inherently bounded by `max_tokens`
- HTTP fallback (Ollama, LM Studio API) could theoretically return unbounded data
- 256KB is ~64K tokens at 4 chars/token -- far more than any reasonable response
- Simple `len()` check on response body, no streaming complexity

### D6: Validators as pure functions, not middleware

**Decision:** `validators.py` exports pure functions (`validate_path()`,
`validate_command()`) called explicitly in each tool, not a middleware/decorator layer.

**Why:**
- Matches existing codebase pattern (tools.py calls validation inline)
- Each tool has different validation needs (read vs. write, path vs. URL)
- No magic -- grep for `validate_path` shows exactly which tools are protected
- Easier to test (pure input/output, no request context needed)

## Architecture

```
Tool call from AgentLoop
    |
    v
tool_registry.execute()
    |
    +-- Check risk level (HIGH/MED/LOW from tool definition)
    |
    +-- HIGH risk? --> Route to pending_approvals (HITL flow)
    |                   |
    |                   +-- Toast: "run_python wants to execute [snippet]"
    |                   +-- Wait for Approve/Deny (timeout 60s)
    |                   +-- Denied? --> Return structured error
    |
    +-- Call tool implementation
    |       |
    |       +-- validate_path() for file ops
    |       +-- validate_command() for exec ops
    |       +-- (existing validation: URL scheme, length, control chars)
    |
    +-- Log to audit_log.append(tool, params, result, duration)
    |
    v
Return result to AgentLoop
```

## Risk Classification (existing + new gates)

| Risk | Tools | Gate |
|------|-------|------|
| **HIGH** | `run_python`, `run_powershell`, `run_cmd`, `delete_file` | Approval required |
| **MEDIUM** | `write_file`, `move_file`, `fetch_url`, `clipboard_write` | Path/URL validation |
| **LOW** | Everything else (read-only, memory, git, search) | No gate (audit only) |
