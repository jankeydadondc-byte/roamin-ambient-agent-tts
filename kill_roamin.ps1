# kill_roamin.ps1 — cleanly terminate all Roamin processes (whole trees)
# Uses taskkill /T /F to kill parent + all children so nothing is left orphaned.

$repoRoot = "C:\AI\roamin-ambient-agent-tts"
$lockFile  = "$repoRoot\logs\_wake_listener.lock"
$apiLock   = "$repoRoot\logs\_control_api.lock"
$discovery = "$repoRoot\.loom\control_api_port.json"

$pidsToKill = @{}

# Layer 1: PID lock files (fastest path — written by both processes at startup)
foreach ($f in @($lockFile, $apiLock)) {
    if (Test-Path $f) {
        try {
            $lockPid = [int](Get-Content $f -Raw).Trim()
            if ($lockPid -gt 0) { $pidsToKill[$lockPid] = $f }
        } catch {}
    }
}

# Layer 2: Discovery file (written by control_api with port info)
if (Test-Path $discovery) {
    try {
        $data = Get-Content $discovery -Raw | ConvertFrom-Json
        $lockPid = [int]$data.pid
        if ($lockPid -gt 0) { $pidsToKill[$lockPid] = "discovery" }
    } catch {}
}

# Layer 3: Command-line scan — catches anything that slipped through
$patterns = @("run_wake_listener.py", "run_control_api.py")
try {
    Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object { $cmd = $_.CommandLine; $patterns | Where-Object { $cmd -like "*$_*" } } |
        ForEach-Object { $pidsToKill[$_.ProcessId] = $_.CommandLine }
} catch {
    # CimInstance unavailable — fall back to WMI
    Get-WmiObject Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $cmd = $_.CommandLine; $patterns | Where-Object { $cmd -like "*$_*" } } |
        ForEach-Object { $pidsToKill[$_.ProcessId] = $_.CommandLine }
}

if ($pidsToKill.Count -eq 0) {
    Write-Host "[Roamin] No running Roamin processes found." -ForegroundColor Gray
} else {
    Write-Host "[Roamin] Killing $($pidsToKill.Count) process(es) + their children..." -ForegroundColor Yellow
    foreach ($killPid in $pidsToKill.Keys) {
        # /T kills the entire process tree; /F forces immediate termination
        & taskkill /PID $killPid /T /F 2>&1 | Out-Null
        Write-Host "  [killed] PID $killPid" -ForegroundColor Red
    }
    Start-Sleep -Milliseconds 500
}

# Remove stale lock / discovery files
foreach ($f in @($lockFile, $apiLock, $discovery)) {
    Remove-Item $f -Force -ErrorAction SilentlyContinue
}
Write-Host "[Roamin] Done. All lock files cleared." -ForegroundColor Green
