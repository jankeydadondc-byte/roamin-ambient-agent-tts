Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*roamin-chat*' } | ForEach-Object {
    Write-Host "Killing PID $($_.ProcessId): $($_.ExecutablePath)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
