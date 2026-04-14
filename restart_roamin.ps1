# restart_roamin.ps1 — stop all Roamin processes then relaunch
# Kills entire process trees (taskkill /T /F) so no orphans survive.

$repoRoot  = "C:\AI\roamin-ambient-agent-tts"
$lockFile  = "$repoRoot\logs\_wake_listener.lock"
$apiLock   = "$repoRoot\logs\_control_api.lock"
$discovery = "$repoRoot\.loom\control_api_port.json"
$python    = "$repoRoot\.venv\Scripts\python.exe"

# ── 1. Kill everything ──────────────────────────────────────────────────────

$pidsToKill = @{}

foreach ($f in @($lockFile, $apiLock)) {
    if (Test-Path $f) {
        try {
            $lockPid = [int](Get-Content $f -Raw).Trim()
            if ($lockPid -gt 0) { $pidsToKill[$lockPid] = $f }
        } catch {}
    }
}

if (Test-Path $discovery) {
    try {
        $data = Get-Content $discovery -Raw | ConvertFrom-Json
        $lockPid = [int]$data.pid
        if ($lockPid -gt 0) { $pidsToKill[$lockPid] = "discovery" }
    } catch {}
}

$patterns = @("run_wake_listener.py", "run_control_api.py")
try {
    Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object { $cmd = $_.CommandLine; $patterns | Where-Object { $cmd -like "*$_*" } } |
        ForEach-Object { $pidsToKill[$_.ProcessId] = $_.CommandLine }
} catch {
    Get-WmiObject Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $cmd = $_.CommandLine; $patterns | Where-Object { $cmd -like "*$_*" } } |
        ForEach-Object { $pidsToKill[$_.ProcessId] = $_.CommandLine }
}

if ($pidsToKill.Count -gt 0) {
    Write-Host "[Roamin] Stopping $($pidsToKill.Count) process(es)..." -ForegroundColor Yellow
    foreach ($killPid in $pidsToKill.Keys) {
        & taskkill /PID $killPid /T /F 2>&1 | Out-Null
        Write-Host "  [killed] PID $killPid" -ForegroundColor Red
    }
}

foreach ($f in @($lockFile, $apiLock, $discovery)) {
    Remove-Item $f -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2

# ── 2. Relaunch ─────────────────────────────────────────────────────────────

Write-Host "[Roamin] Starting wake listener..." -ForegroundColor Green
Start-Process -FilePath $python `
              -ArgumentList "run_wake_listener.py" `
              -WorkingDirectory $repoRoot `
              -WindowStyle Normal

# Wait for wake_listener to write the PID lock (up to 10s)
$elapsed = 0
while ($elapsed -lt 10) {
    Start-Sleep -Milliseconds 500
    $elapsed += 0.5
    if (Test-Path $lockFile) {
        $lockPid = (Get-Content $lockFile -Raw).Trim()
        if ($lockPid -match '^\d+$') {
            Write-Host "[Roamin] Wake listener started (PID $lockPid)." -ForegroundColor Cyan
            break
        }
    }
}

# Wait for control_api lock (up to 15s — it starts slightly after wake_listener)
$elapsed = 0
while ($elapsed -lt 15) {
    Start-Sleep -Milliseconds 500
    $elapsed += 0.5
    if (Test-Path $apiLock) {
        $lockPid = (Get-Content $apiLock -Raw).Trim()
        if ($lockPid -match '^\d+$') {
            Write-Host "[Roamin] Control API started (PID $lockPid)." -ForegroundColor Cyan
            break
        }
    }
}

Write-Host "[Roamin] Restart complete." -ForegroundColor Green
