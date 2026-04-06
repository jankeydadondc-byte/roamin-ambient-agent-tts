# Testing & CI notes for Control Panel change

This document summarizes existing test artifacts, how to run them locally, and recommended CI improvements for the `ux-plugins-control-panel-next` change.

## Existing artifacts

- `tests/test_e2e_smoke.py` — pytest smoke test that exercises `POST /plugins/install` and polls `GET /task-history` until the task completes.
- `.github/workflows/e2e-smoke.yml` — lightweight workflow to start the Control API and run pytest; uploads `control_api.log` on failure.

## How to run locally (quick)

1. Activate venv and install deps (if not already):

```powershell
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ui/control-panel
npm install
```

1. Start the Control API (in background):

```powershell
.venv\Scripts\python.exe run_control_api.py &
```

1. Run the smoke pytest:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_e2e_smoke.py
```

1. Optionally start the SPA dev server to visually inspect the UI:

```powershell
cd ui/control-panel
npm run dev
```

## Recommended CI improvements

1. Add a Playwright job (browser E2E)
   - Start the Control API as a service in the job.
   - Start the SPA dev server (or serve the `dist` build) and run Playwright tests against `http://localhost:5173`.
   - Record Playwright traces and screenshots on failure.

2. Keep the existing pytest smoke job for fast feedback.

3. Artifact collection
   - On failure, upload `control_api.log`, Playwright traces, and test output XML for easier debugging.

4. Flaky test mitigation
   - Retry failing Playwright tests up to 1 time in CI; investigate infra flakiness rather than silencing failures.

## Recommended test matrix

- Unit tests (fast): run on each PR.
- Smoke pytest (fast): run on each PR.
- Playwright browser E2E (slower): run nightly or on release branches and optionally on PRs with `e2e` label.

## Notes on environment parity

- Use a lightweight fixture for the Control API that can run in CI (no GPU/model heavy deps). The current control API supports a `dummy` model; ensure CI uses a headless, minimal config.
- For WebSocket assertions, tests should assert the presence of expected `task_update` or `plugin_event` messages and fall back to polling the REST `GET /task-history` if WS events are missed.

---

If you want, I can scaffold a Playwright test and a CI job next. Which do you prefer me to implement first: the Playwright tests or the CI job integration?
