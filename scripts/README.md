# Smoke test script

This script performs a quick local end-to-end smoke test for the Control API:

- Posts a plugin install to `/plugins/install`
- Polls `/task-history` until the install task appears (or times out)

Prerequisites

- A running Control API (default: `http://127.0.0.1:8765`). Start with:

  PowerShell

  & .venv\Scripts\Activate.ps1
  .venv\Scripts\python.exe run_control_api.py

  Unix / macOS

  source .venv/bin/activate
  python3 run_control_api.py

- (Optional) Start the SPA dev server at `ui/control-panel` for manual UI verification:

  cd ui/control-panel
  npm install
  npm run dev

Run the smoke script

PowerShell

  & .venv\Scripts\Activate.ps1
  .venv\Scripts\python.exe scripts\smoke_test_install.py

Unix / macOS

  source .venv/bin/activate
  python3 scripts/smoke_test_install.py

Expected output

- The script will print the install response (including a `task_id`) and then poll `/task-history` until it finds the task. It prints `Result: OK` on success and exits non‑zero on failure.

Notes

- This script is intended for local development and manual CI debugging. We'll add a proper pytest E2E test later for CI integration.
