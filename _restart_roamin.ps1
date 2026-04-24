# _restart_roamin.ps1 — Kill all Roamin processes and start fresh.
# Run this from PowerShell (or double-click) to restart Roamin cleanly.

$projectRoot = "C:\AI\roamin-ambient-agent-tts"
$lockFile    = "$projectRoot\logs\_wake_listener.lock"
$vbs         = "$projectRoot\_start_wake_listener.vbs"

Write-Host "[Restart] Killing Roamin processes..." -ForegroundColor Cyan

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -like "*run_wake_listener*" -or
        $_.CommandLine -like "*run_control_api*"
    } |
    ForEach-Object {
        Write-Host "[Restart]   Killing PID $($_.ProcessId) — $($_.CommandLine.Substring(0, [Math]::Min(80, $_.CommandLine.Length)))"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Start-Sleep -Seconds 2

if (Test-Path $lockFile) {
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    Write-Host "[Restart] Lock file removed."
}

Write-Host "[Restart] Starting Roamin..." -ForegroundColor Green
& wscript.exe $vbs
