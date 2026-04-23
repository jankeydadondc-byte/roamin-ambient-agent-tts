$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$path = Join-Path $desktop "RoaminControlPanel.lnk"
$lnk = $ws.CreateShortcut($path)
Write-Host "TARGET: $($lnk.TargetPath)"
Write-Host "ARGS: $($lnk.Arguments)"
Write-Host "WORKDIR: $($lnk.WorkingDirectory)"
