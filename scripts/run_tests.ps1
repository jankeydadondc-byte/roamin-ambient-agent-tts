# scripts/run_tests.ps1
# Run the test‑suite after installing missing deps

Write-Host "Installing required packages…"
pip install numpy fastapi | Out-Null          # installs both libs quietly
Write-Host "pip exit code: $LASTEXITCODE"

Write-Host "Verifying agent.core import …"
python -c "import agent.core; print(agent.core.AgentLoop)" | Out-Null
Write-Host "pytest exit code: $LASTEXITCODE"

Write-Host "Running all tests quietly…"
pytest -q
Write-Host "pytest exit code: $LASTEXITCODE"
