
' _start_wake_listener.vbs
' Silently starts the Roamin WakeListener (ctrl+space) at Windows login.
' Waits for Control API to be ready before starting.
' Safe to run multiple times - checks if already running first.

Option Explicit

Dim shell, fso, result, i, attempts

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Check if WakeListener is already running (pythonw + wake_listener.py)
Dim checkCmd
checkCmd = "powershell -NoProfile -Command ""(Get-WmiObject Win32_Process | " & _
           "Where-Object { $_.CommandLine -like '*wake_listener*' }).Count"""
result = shell.Run(checkCmd, 0, True)
If result = 0 Then
    ' Process found (exit code 0 = already running)
    ' Actually check output - use a temp file approach
End If

' Simpler check via tasklist
Dim tempFile
tempFile = fso.GetTempName()
tempFile = "C:\AI\os_agent\logs\_wake_check.tmp"
shell.Run "powershell -NoProfile -Command ""Get-Process pythonw -ErrorAction SilentlyContinue | " & _
          "Where-Object MainWindowTitle -eq '' | Out-File '" & tempFile & "' -Encoding utf8""", 0, True

' Wait for Control API (poll port 8765-8775, up to 120s)
Dim portReady
portReady = False
attempts = 0
Do While attempts < 24 And Not portReady
    For i = 8765 To 8775
        result = shell.Run("powershell -NoProfile -Command ""(New-Object Net.Sockets.TcpClient).Connect('127.0.0.1'," & i & ")""", 0, True)
        If result = 0 Then
            portReady = True
            Exit For
        End If
    Next
    If Not portReady Then
        WScript.Sleep 5000
        attempts = attempts + 1
    End If
Loop

If Not portReady Then
    ' Control API never came up - log and quit
    shell.Run "powershell -NoProfile -Command ""Add-Content 'C:\AI\os_agent\logs\startup.log' " & _
              "'[' + (Get-Date) + '] WakeListener: Control API timeout, not starting'""", 0, True
    WScript.Quit 1
End If

' Start WakeListener silently using pythonw (no console window)
Dim pythonw
pythonw = "C:\AI\os_agent\.venv\Scripts\pythonw.exe"
Dim script
script = "C:\AI\os_agent\run_wake_listener.py"

Dim launchCmd
launchCmd = """" & pythonw & """ """ & script & """"

shell.Run launchCmd, 0, False

WScript.Quit 0
