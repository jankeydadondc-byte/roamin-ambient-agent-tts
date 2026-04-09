# Proposal: Priority 8 — Performance & Scalability Optimization

## Why This Matters

Roamin is currently stable and secure (Phase 7 complete). But its current architecture has two bottlenecks:

1. **Blocking I/O operations** — Web search, file reads, and git CLI calls freeze the UI during execution
2. **No resource visibility or throttling** — Agent can't self-protect when resources are exhausted

This proposal implements async I/O + resource monitoring to eliminate freezes and add robustness.

---

## Scope: What We're Implementing (and Not)

### ✅ Included (Milestones 1–3)

| Milestone | What | Why |
|---|---|---|
| **1. Async Execution** | Replace `ThreadPoolExecutor` with `asyncio.gather()` for tool execution | Eliminates UI freeze during web search/file ops |
| **2. Resource Monitoring** | Add CPU/GPU/RAM checks + throttle on exhaustion | Prevents agent crashes under load |
| **3. Task Cleanup** | SQLite cleanup for old tasks (>24h retention) | Prevents database bloat and memory leaks |

### ❌ Deferred (Milestone 4)

| Milestone | What | Why Defer? |
|---|---|---|
| **KV Cache Quantization** | q8_0 KV cache to save VRAM | Accuracy tradeoff not worth it with >15GB headroom |

---

## Technical Design

### New Files

| File | Purpose |
|---|---|
| `agent/core/async_utils.py` | Shared async primitives: retry, timeout, resource checks |
| `agent/core/resource_monitor.py` | CPU/GPU/RAM monitoring + throttle decision logic |

### Modified Files

| File | Changes |
|---|---|
| `agent/core/agent_loop.py` | Refactor `_execute_step()` → use `asyncio.gather(*coroutines)` |
| `agent/control_api.py` | Add `/health` endpoint (`{cpu, ram_mb, vram_mb, throttled}`) |
| `run_wake_listener.py` | Schedule cleanup task every 5 min |

---

## Risk Assessment

| Risk Type | Severity | Mitigation |
|---|---|---|
| **Breaking Change** (async refactor) | ⚠️⚠️ (2/5) | Feature flag `ROAMIN_USE_ASYNC` (default off), gradual rollout |
| **Performance Impact** | Neutral (may improve) | No guarantee until benchmarked; no regression expected |
| **Security Risk** | None | Async operations don't expose new attack surface |

---

## Testing Strategy

- **Unit Tests**: pytest + asyncio fixtures for all async utilities, resource checks
- **Integration Tests**: `/health` endpoint and task cleanup API via Control API
- **Target**: 250/261 tests passing (add ~40 new tests)

---

## Acceptance Criteria

- [ ] All Milestones 1–3 implemented and committed
- [ ] Test suite ≥250/261 passing (add ~40 new tests)
- [ ] `/health` endpoint returns CPU/RAM/VRAM + throttle status
- [ ] Control Panel "Health" tab visualizes resource usage
- [ ] OpenSpec proposal archived to `openspec/archive/priority-8-performance-scalability/`

---

## Implementation Timeline

| Day | Milestone | Hours | Output |
|---|---|---|---|
| Day 1 | Milestone 1: Async execution | 5h | `async_utils.py`, refactor `_execute_step()` |
| Day 2 | Milestone 2: Resource monitoring | 4h | `resource_monitor.py`, `/health` endpoint |
| Day 3 | Milestone 3: Task cleanup | 2h | Cleanup task, SQLite retention window |
| Day 4 | Testing & documentation | 4h | 250+ tests passing, docs updated |

**Total:** ~15 hours of focused work

---

## Next Steps

- [ ] Implement Milestones 1–3 sequentially
- [ ] Add async_utils.py and resource_monitor.py
- [ ] Refactor agent_loop.py to use asyncio.gather()
- [ ] Test `/health` endpoint in Control Panel
- [ ] Archive OpenSpec proposal to archive/

---

## References

- Current test suite: 210/211 passing
- Phase 7 (Security) complete
- Priority 8 is the logical next step after stability + UX enhancements
