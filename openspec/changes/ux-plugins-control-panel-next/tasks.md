# Task list — ux-plugins-control-panel-next

1. Plugin manifest confirmation UI — COMPLETED
   - File(s): `ui/control-panel/src/components/PluginActions.jsx`, `ui/control-panel/src/components/CapabilityHints.jsx`
   - Owner: frontend
   - Estimate: 2 days
   - Notes: confirmation flow implemented; UI shows manifest + `requestedCapabilities` and requires explicit Accept.

2. Task History UI + wiring — BASIC IMPLEMENTED
   - File(s): `ui/control-panel/src/components/TaskHistory.jsx`, `ui/control-panel/src/components/Sidebar.jsx`
   - Owner: frontend
   - Estimate: 2 days
   - Notes: listing, filter, pagination, and live `task_update` handling implemented. UX polishing (detailed view, server pagination) remains.

3. API client: API key + WS reconnection — COMPLETED
   - File(s): `ui/control-panel/src/apiClient.js`, `ui/control-panel/src/components/Header.jsx`
   - Owner: frontend
   - Estimate: 1.5 days
   - Notes: `setApiKey()` added; WS reconnect/backoff implemented and header shows WS status.

4. E2E tests (install → task → plugin_event → action) — PARTIAL
   - File(s): `tests/test_e2e_smoke.py` (pytest smoke), `tests/e2e/install_flow.spec.ts` (playwright suggested)
   - Owner: infra
   - Estimate: 2 days
   - Notes: smoke pytests added and pass locally; full Playwright browser E2E coverage is recommended and pending.

5. Accessibility audit (axe-core) — NOT STARTED
   - Owner: frontend
   - Estimate: 1 day

6. Playwright browser E2E (new)
   - File(s): `tests/e2e/` + CI job in `.github/workflows/`
   - Owner: infra/frontend
   - Estimate: 2 days
   - Notes: cover install→task→plugin_event→action in a browser environment; assert WS-driven UI updates.

7. Archive OpenSpec change (new)
   - File(s): `openspec/changes/archive/ux-plugins-control-panel-next/` (create final_report.md)
   - Owner: docs
   - Estimate: 0.5 day
   - Notes: move final proposal + checklist into archive once remaining items are done.

8. Small follow-ups
   - Add `CapabilityHints.jsx` and small UX copy for capability risks.
   - Improve `Supervisor` restart semantics in a follow-up.
