# Tasks — Remaining Control Panel Work

## Status

Items 3 and 4 are COMPLETE. Items 1, 2, and 5 are deferred (discussed with user — not blocking for current scope).

---

## Item 1 — Playwright Browser E2E Tests (WON'T DO — personal tool)

**Decision:** Won't implement for current scope. Personal local tool with one user;
cost/benefit is inverted. API-level smoke tests + unit tests (53 passing) cover the
critical paths. Manual browser check is the feedback loop.

**If shipped:** Dev note added to `run_wake_listener.py` (top of file) — checklist
item to scaffold `tests/e2e/playwright/install_flow.spec.ts` and add a headless
browser CI job before any public/multi-user release.

---

## Item 2 — Accessibility Audit & Remediation (PARTIAL — no CI gate)

**Decision:** One-time manual scan yes; CI gate no.
- Run: `npx axe-cli http://localhost:5173` when needed
- No CI gate — VS Code dark palette is intentionally below some WCAG ratios, and
  gating on zero violations would create maintenance friction for a personal tool.
- **If shipped:** Add axe gate to the Playwright CI job (see Item 1 dev note).

---

## Item 3 — Task History Server Pagination + UX Polish (COMPLETE)

- [x] `memory_store.get_task_runs()` — add `offset` + `task_type` params, use `LIMIT ? OFFSET ?`
- [x] `memory_store.count_task_runs()` — new method, counts rows matching same filters
- [x] `memory_manager.query_tasks()` — returns `{tasks, total, page, per_page, pages}` dict
- [x] `control_api.py /task-history` — accepts `page`, `per_page`, `task_type`, `q`; returns pagination envelope
- [x] `apiClient.js getTaskHistory()` — accepts options object `{page, perPage, status, taskType, since, q}`
- [x] `TaskHistory.jsx` — full rewrite:
  - Server-side pagination state (page, totalPages, total, loading)
  - Filter bar: keyword input, status select, task-type input, since-date picker
  - Table with clickable rows that expand to show detail (goal, type, steps, started, finished, error)
  - Status-coloured status column (green=completed, red=failed, blue=running, orange=pending)
  - Pagination controls: « ‹ page/totalPages › » buttons
  - Fallback to prop tasks on fetch error

---

## Item 4 — CI Integration & Artifact Collection (COMPLETE)

- [x] `.github/workflows/e2e-smoke.yml` → renamed to `CI` workflow with two jobs:
  - `unit` job: runs `pytest -q tests/unit/` (fast, no server required), uploads `.pytest_cache/` on failure
  - `e2e` job: needs `unit`, starts Control API, waits for `/status`, runs `pytest -q tests/test_e2e_smoke.py`, uploads `control_api.log` on failure
- [x] Updated `actions/setup-python` to v5

---

## Item 5 — Docs & Release Notes (PENDING)

- [ ] Finalize `openspec/changes/ux-plugins-control-panel-next/spec.md`
- [ ] Create `RELEASE_NOTES.md` describing behavior changes and upgrade notes

*Low priority — can be done at archive time.*

---

## Verification

```
pytest tests/unit/ tests/test_control_api.py -q
# 53 passed — 2026-04-10
```
