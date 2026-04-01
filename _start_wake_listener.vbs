Option Explicit

Dim shell, fso, pythonw, script, workingDir, logFile, pid

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Paths (all in NEW repo)
pythonw = "C:\AI\roamin-ambient-agent-tts\.venv\Scripts\pythonw.exe"
script = "C:\AI\roamin-ambient-agent-tts\run_wake_listener.py"
workingDir = "C:\AI\roamin-ambient-agent-tts"
logFile = "C:\AI\roamin-ambient-agent-tts\logs\startup.log"

' Single-instance guard: check lock file first (faster, handles startup race before WMI updates)
Dim lockPath, lockPid
lockPath = "C:\AI\roamin-ambient-agent-tts\logs\_wake_listener.lock"
If fso.FileExists(lockPath) Then
    On Error Resume Next
    Dim lf
    Set lf = fso.OpenTextFile(lockPath, 1)
    lockPid = Trim(lf.ReadAll())
    lf.Close
    On Error GoTo 0
    If lockPid <> "" And IsNumeric(lockPid) Then
        If IsPidRunning(CLng(lockPid)) Then
            WScript.Quit 0
        End If
    End If
End If

' Fallback: WMI process scan (catches processes that haven't written lock file yet)
If IsProcessRunning("run_wake_listener") Then
    WScript.Quit 0
End If

' Wait for Chatterbox TTS API (optional, ports 4123-4129)
WaitForChatterbox

' Launch WakeListener in background window (style=0 = hidden)
Dim result
result = shell.Run("""" & pythonw & """ """ & script & """", 0, False)

' Log startup
WriteLog "WakeListener started PID: " & result

Function IsPidRunning(pid)
    Dim wmi, procs
    On Error Resume Next
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    Set procs = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE ProcessId=" & pid)
    IsPidRunning = (procs.Count > 0)
    On Error GoTo 0
End Function

Function IsProcessRunning(processName)
    Dim wmi, processes, process, count
    count = 0
    On Error Resume Next
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    Set processes = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe'")
    For Each process In processes
        If InStr(process.CommandLine, processName) > 0 Then
            count = count + 1
        End If
    Next
    On Error GoTo 0
    IsProcessRunning = (count > 0)
End Function

Sub WaitForChatterbox()
    Dim attempts, port, url, http

    For attempts = 1 To 20
        For port = 4123 To 4129
            url = "http://127.0.0.1:" & port & "/health"
            On Error Resume Next
            Set http = CreateObject("MSXML2.XMLHTTP")
            http.Open "GET", url, False
            http.Send
            If http.Status = 200 Then
                Set http = Nothing
                Exit Sub
            End If
            On Error GoTo 0
            Set http = Nothing
        Next
        WScript.Sleep 3000
    Next
End Sub

Sub WriteLog(message)
    Dim logPath, dir, f, timestamp
    logPath = "C:\AI\roamin-ambient-agent-tts\logs\startup.log"

    ' Ensure logs directory exists
    dir = fso.GetParentFolderName(logPath)
    If Not fso.FolderExists(dir) Then
        fso.CreateFolder dir
    End If

    timestamp = Now()
    On Error Resume Next
    Set f = fso.OpenTextFile(logPath, 8, True)
    f.WriteLine timestamp & " - " & message
    f.Close
    On Error GoTo 0
End Sub
