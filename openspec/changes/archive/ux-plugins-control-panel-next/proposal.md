# Proposal: Next steps for Control Panel — Manifest confirmation, tasks, WS, auth, tests

## Goal

Implement the prioritized UI and infra improvements needed for the Control Panel MVP so the SPA and Control API meet the acceptance criteria in the current spec and are ready for reliable integration testing.

## Prioritized Items

1. Manifest confirmation UI (HIGH) — IMPLEMENTED
   - After `POST /plugins/validate` returns valid, show the manifest contents including `requestedCapabilities` and `description`.
   - Require the user to explicitly confirm (Accept) before calling `POST /plugins/install`.
   - Display capability risk hints inline.

2. Task History UI + `task_update` handling (MEDIUM) — IMPLEMENTED (basic)
   - Add a `Task History` panel reachable from the Sidebar.
   - Show tasks from `GET /task-history` and update items in real time using `task_update` WS messages.

3. WebSocket client improvements (MEDIUM) — IMPLEMENTED (reconnect + status events)
   - Add reconnect/backoff strategy, `onopen`/`onclose` handlers, and a visible WS status indicator in the header.
   - Support sending the API key header on WS handshake if configured.

4. API key support (MEDIUM) — IMPLEMENTED
   - Expose `setApiKey(token)` in `apiClient.js` and attach header to all REST calls and WS connects.
   - Add a secure input in `Header.jsx` (toggle hidden) to set/clear the key locally.

5. E2E acceptance tests (MEDIUM) — PARTIAL (pytest smoke test added + GH Action)
   - Add test scripts (playwright or pytest+playwright) to exercise install → task → plugin_event → enable/disable flows.
   - Test expectations: install returns 202 and task id; task history contains the task; WS emits plugin_event; plugin appears in `GET /plugins` and `POST /plugins/{id}/action` works.

6. Accessibility audit (LOW) — NOT STARTED

## OpenSpec completion status

- Milestone 1 (manifest confirmation) — Completed and verified locally. UI flow requires explicit confirmation and displays `requestedCapabilities` with inline hints.
- Milestone 2 (task history + WS) — Basic listing, live updates, filtering and pagination implemented; UX polishing remains.
- Milestone 3 (WS + API key) — Reconnect/backoff and header UI implemented; WS status wired to header indicator.
- Milestone 4 (E2E & CI) — Smoke-level pytest test added and a minimal GitHub Actions job created; workflow includes artifact upload on failure. Full Playwright coverage is not yet added.

## Acceptance checklist (for marking this OpenSpec change complete)

- [x] Manifest confirmation UI implemented and manual-verified with `POST /plugins/validate` → `POST /plugins/install` flow.
- [x] Task History panel present, wired to `GET /task-history` and `task_update` WS messages.
- [x] Reconnecting WS client with backoff and UI indicator in header.
- [x] API key support implemented in `apiClient.js` and header UI, persisted to `localStorage` for convenience.
- [x] Smoke-level E2E test (`tests/test_e2e_smoke.py`) added and passing locally.
- [ ] Full Playwright-based E2E coverage for install→task→plugin_event→action (CI integration required).
- [ ] Accessibility audit run and high-severity issues fixed.

## CI / Testing notes

- The repository now contains `tests/test_e2e_smoke.py` which exercises the install→task lifecycle against the running control API. The GitHub Action `.github/workflows/e2e-smoke.yml` will start the control API, run pytest and upload `control_api.log` on failure. This is intentionally lightweight to avoid long-running CI steps.
- Recommendation: add a Playwright job that runs the SPA in dev server mode, runs browser-based E2E tests asserting WS events and UI updates, and records traces for flaky investigations.

## Next steps (recommended)

1. Add Playwright E2E tests covering plugin enable/disable and WS event assertions; wire into CI.
2. Run an accessibility audit (axe-core) against the built SPA; fix high-severity issues.
3. Polish Task History UX: detailed task view, server-side pagination if needed, and richer task filtering.
4. When the above are complete, move this change into `openspec/changes/archive/` with the final report.

---

If you want, I can implement the Playwright E2E job and the accessibility audit next. Otherwise I will archive this OpenSpec change and open issues for the remaining items.

- Run axe-core (or similar) against the SPA and fix any high-severity accessibility issues.

## Acceptance criteria (per item)

- Manifest confirmation: UI displays manifest fields + `requestedCapabilities` and requires explicit user confirmation before POST /plugins/install. (DONE)
- Task history: panel lists tasks and updates status in <5s after `task_update` messages. (BASIC UI DONE — UX refinement pending)
- WS: client reconnects automatically; header indicator shows connected/connecting/disconnected. (DONE)
- API key: REST requests and WS include `x-roamin-api-key` when set; header UI persists locally in `localStorage` for convenience. (DONE)
- E2E: tests pass in CI environment (or locally) against the prototype control API. (SMOKE TEST + ACTION ADDED — CI validation required)

## Milestones & Implementation Plan

Milestone 1 — Manifest confirmation UI (2 days)

- Edit `PluginActions.jsx` to call `/plugins/validate`, render a confirmation modal or inline details showing manifest + capabilities, require user Accept to call `/plugins/install`.
- Add small `CapabilityHints.jsx` helper mapping capability → short risk text.
- Tests: unit test for the `PluginActions` confirmation flow.

Milestone 2 — Task History UI + WS wiring (2 days)

- Add `TaskHistory.jsx` component and `task-history` Sidebar link.
- Use `GET /task-history` on load and subscribe to `task_update` WS events to update statuses.
- Tests: script that asserts task record lifecycle after install.

Milestone 3 — WebSocket & API key improvements (1.5 days)

- Extend `apiClient.js` with `setApiKey()` and WS reconnect/backoff (exponential, capped).
- Add header indicator component in `Header.jsx` and wire WS status events.

Milestone 4 — E2E tests & accessibility (2 days)

- Add Playwright tests; integrate with CI later.
- Run axe-core audit and fix high-priority issues.

## Risks & Mitigations

- UX friction if manifest confirmation blocks installs: keep the confirmation minimal and allow advanced users to opt-out via a small checkbox in dev mode.
- WS reconnection may flood the API: use exponential backoff and jitter.

## Tasks (concrete)

- `PluginActions.jsx`: show manifest modal + confirm before install (owner: frontend)
- `CapabilityHints.jsx`: mapping component (owner: frontend)
- `TaskHistory.jsx`: UI + wiring to `/task-history` (owner: frontend)
- `apiClient.js`: add `setApiKey()` and enhanced WS logic (owner: frontend)
- `Header.jsx`: add WS status + API key toggle (owner: frontend)
- `tests/e2e/*`: Playwright scripts for install→task→plugin_event→action (owner: infra)
- `ci/`: test integration notes (owner: infra)

---

If you approve, I will implement Milestone 1 now (add manifest confirmation UI), create a small unit test, and open a PR. Otherwise I can open issues instead and implement later.

Resources (this change):

- Spec: `spec.md`
- Tasks: `tasks.md`
- Architecture diagram: `architecture.md`
- Testing & CI notes: `testing_and_ci.md`
