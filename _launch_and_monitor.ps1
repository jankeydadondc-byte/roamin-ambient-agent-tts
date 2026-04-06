# Roamin Launch & Monitor
# Kills duplicate instances, clears log, launches Roamin, tails the log filtered.
# Usage: Right-click > Run with PowerShell, or from Admin PS: .\launch_and_monitor.ps1

$repoRoot  = "C:\AI\roamin-ambient-agent-tts"
$lockFile  = "$repoRoot\logs\_wake_listener.lock"
$logFile   = "$repoRoot\logs\wake_listener.log"
$pythonw   = "$repoRoot\.venv\Scripts\pythonw.exe"
$script    = "$repoRoot\run_wake_listener.py"
$apiScript = "$repoRoot\run_control_api.py"
$discoveryFile = "$repoRoot\.loom\control_api_port.json"

Write-Host "[Roamin] Checking for existing instances..." -ForegroundColor Yellow

# Kill all existing wake_listener and control_api processes
$killed = 0
Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like "*run_wake_listener*" -or $_.CommandLine -like "*run_control_api*" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    $killed++
}
if ($killed -gt 0) {
    Write-Host "[Roamin] Killed $killed existing instance(s)" -ForegroundColor Red
    Start-Sleep -Seconds 1
}

# Remove stale lock and discovery file
Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
Remove-Item $discoveryFile -Force -ErrorAction SilentlyContinue

# Clear log
"" | Out-File $logFile -Encoding utf8
Write-Host "[Roamin] Log cleared" -ForegroundColor Gray

# Launch Roamin (hidden, backgrounded)
Start-Process $pythonw -ArgumentList $script -WorkingDirectory $repoRoot -WindowStyle Hidden
Write-Host "[Roamin] Launched. Waiting for warmup..." -ForegroundColor Green

# Launch Control API (use python.exe not pythonw to capture output; will minimize window)
$python = "$repoRoot\.venv\Scripts\python.exe"
$apiLog = "$repoRoot\logs\control_api.log"
Start-Process $python -ArgumentList $apiScript -WorkingDirectory $repoRoot -WindowStyle Minimized -RedirectStandardOutput $apiLog -RedirectStandardError $apiLog
Write-Host "[Control API] Launched (log: logs/control_api.log)" -ForegroundColor Green

# Wait for "Ready" to appear in log (up to 120s)
$timeout = 120
$elapsed = 0
while ($elapsed -lt $timeout) {
    Start-Sleep -Seconds 2
    $elapsed += 2
    if (Test-Path $logFile) {
        $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
        if ($content -match "Ready\. Press ctrl\+space") {
            Write-Host "[Roamin] READY after ${elapsed}s" -ForegroundColor Cyan
            break
        }
        # Show warmup progress
        $lastLine = (Get-Content $logFile -Tail 1 -ErrorAction SilentlyContinue)
        if ($lastLine) {
            Write-Host "  $lastLine" -ForegroundColor DarkGray
        }
    }
}
if ($elapsed -ge $timeout) {
    Write-Host "[Roamin] WARNING: Timed out waiting for Ready" -ForegroundColor Red
}

# Check Control API readiness (should already be up by now)
$apiElapsed = 0
while ($apiElapsed -lt 15) {
    if (Test-Path $discoveryFile) {
        $apiInfo = Get-Content $discoveryFile | ConvertFrom-Json
        Write-Host "[Control API] Ready on port $($apiInfo.port)" -ForegroundColor Cyan
        break
    }
    Start-Sleep -Seconds 1
    $apiElapsed++
}
if ($apiElapsed -ge 15) {
    Write-Host "[Control API] WARNING: Did not start within 15s" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== LIVE LOG (filtered) ===" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop monitoring (Roamin keeps running)" -ForegroundColor DarkGray
Write-Host ""

# Tail the log, filtering out noise
Get-Content $logFile -Wait -Tail 5 |
    Where-Object {
        $_ -notmatch "DEBUG - (send frame|received frame|encoding|connecting|connected|Browser emulation|Cipher|handshake|ALPN|TLS|binding|pooling|inserting|Using cipher|Not resuming|Final cipher)" -and
        $_ -ne ""
    }
