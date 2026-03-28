
' _start_control_api.vbs
' Silently starts the Roamin Control API at Windows login.
' Safe to run multiple times - checks port 8765 first.

Option Explicit

Dim shell, fso, port, tcp, result

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Check if Control API is already running on any port 8765-8775
Dim portInUse
portInUse = False
Dim i
For i = 8765 To 8775
    On Error Resume Next
    Set tcp = CreateObject("WScript.Shell")
    result = tcp.Run("powershell -NoProfile -Command ""(New-Object Net.Sockets.TcpClient).Connect('127.0.0.1'," & i & ")""", 0, True)
    On Error GoTo 0
    If result = 0 Then
        portInUse = True
        Exit For
    End If
Next

If portInUse Then
    WScript.Quit 0
End If

' Launch Control API via existing PS1 launcher
Dim cmd
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & _
      """C:\AI\os_agent\scripts\launch_control_api_detached_clean.ps1"" -ControlApiOnly"

shell.Run cmd, 0, False

WScript.Quit 0
