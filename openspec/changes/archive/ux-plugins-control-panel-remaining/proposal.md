# Proposal: Remaining high-value work for Control Panel

## Goal

Deliver the remaining high-value items to reach a production-ready Control Panel MVP: robust browser E2E coverage, accessibility compliance, and improved Task History UX with scalable server-side support and CI integration.

## Prioritized Items

1. Playwright browser E2E tests (HIGH)
   - End-to-end scenarios in a real browser covering:
     - Install flow: validate manifest → confirm → install → assert `task_update` and plugin appears in `GET /plugins`.
     - Plugin lifecycle: enable → disable → uninstall.
     - WS resilience: simulate backend restart/disconnect and assert the SPA reconnects and resynchronizes `GET /task-history`.
   - Output: Playwright traces, screenshots, and test reports.

2. Accessibility audit & remediation (HIGH)
   - Run `axe-core` or Playwright + `axe` integration against the built SPA.
   - Fix high/critical issues (contrast, ARIA roles, focus order, labels). Add CI check gating on no critical violations.

3. Task History UX polish (MEDIUM)
   - Detailed task view (expand row or panel) showing logs, metadata and task steps.
   - Server-side pagination support for `GET /task-history` and client paging UI for large histories.
   - Filters: by type, status, plugin id, date range.

4. CI integration & artifact collection (MEDIUM)
   - Add Playwright job to `.github/workflows/` that starts the Control API and SPA, runs tests, and uploads traces + logs on failure.
   - Keep the pytest smoke job for quick feedback.

5. Docs & release notes (LOW)
   - Finalize API docs in `openspec/changes/ux-plugins-control-panel-next/spec.md` and add a short `RELEASE_NOTES.md` describing behavior changes and upgrade notes.

## Acceptance Criteria

- Playwright tests run in CI and pass (or have documented stable flake rate <2%).
- Axe-core reports zero critical/serious violations in CI for the built SPA.
- Task History supports server pagination and the UI can page/filter without excessive client memory use.
- CI uploads Playwright traces, `control_api.log`, and test artifacts on failure.

## Milestones & Estimates

- Milestone 1 — Scaffold Playwright tests and run locally (1.5 days)
  - Add `tests/e2e/playwright/` and a sample `install_flow.spec.ts` implementing the install→task→plugin_event flow.
  - Run locally using `npx playwright test`.

- Milestone 2 — CI job & artifact collection (0.5 day)
  - Add `.github/workflows/e2e-playwright.yml` job.
  - Ensure headless browser runs and artifacts are uploaded on failure.

- Milestone 3 — Accessibility audit + fixes (1 day)
  - Run axe, categorize issues, fix high/critical problems.
  - Add CI axe check (Playwright + axe) to the Playwright job.

- Milestone 4 — Task History server pagination + UI polish (1.5 days)
  - Extend `agent/control_api.py` `GET /task-history` to accept `?page=` + `?per_page=` and return metadata.
  - Add detailed task view and filters to `TaskHistory.jsx`.

- Milestone 5 — Docs & archive (0.5 day)
  - Update `spec.md`, create `RELEASE_NOTES.md`, and archive the new OpenSpec change.

## Risks & Mitigations

- Flaky browser tests: mitigate with retries, Playwright traces, and stable test fixtures.
- CI resource/time cost: run Playwright on scheduled or labeled PRs to reduce load.
- Accessibility fixes may impact UI layout; plan changes with visual regression snapshots.

## Owners & Next Steps

- Owner: frontend + infra collaboration.
- Next immediate step I can take: scaffold the Playwright test (`install_flow.spec.ts`) and add a minimal `.github/workflows/e2e-playwright.yml` job. This will create the baseline for further iterations.

Would you like me to scaffold the Playwright tests and CI job now, or run the accessibility audit first?
