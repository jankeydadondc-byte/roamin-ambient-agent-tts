Option Explicit

Dim shell, fso, pythonw, python, script, workingDir, logFile, pid

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Paths (all in NEW repo)
pythonw = "C:\AI\roamin-ambient-agent-tts\.venv\Scripts\pythonw.exe"
python = "C:\AI\roamin-ambient-agent-tts\.venv\Scripts\python.exe"
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

' Fallback: WMI process scan (catches processes that haven't written lock file yet).
' Note: there is a ~250-500ms race window between this check and the shell.Run below
' where a rapid double-click can slip through. The Python named mutex in
' run_wake_listener.py is the authoritative single-instance guard — this VBS check
' is a best-effort early exit to avoid unnecessary process startup overhead.
If IsProcessRunning("run_wake_listener") Then
    WScript.Quit 0
End If

' Launch Chatterbox TTS API if not already running (voice clone + fast TTS)
' DEV NOTE: To suppress Chatterbox and force SAPI fallback, create logs\.disable-chatterbox
' The flag file causes this script to kill ALL running Chatterbox processes before Roamin starts.
Dim disableChatterboxPath
disableChatterboxPath = "C:\AI\roamin-ambient-agent-tts\logs\.disable-chatterbox"
If fso.FileExists(disableChatterboxPath) Then
    WriteLog "Chatterbox disabled — killing any running instances..."
    KillChatterboxProcesses()
    WriteLog "Chatterbox processes cleared. SAPI fallback will be used."
    ' Do NOT call WaitForChatterbox — we want zero Chatterbox on this boot
ElseIf Not IsChatterboxRunning() Then
    WriteLog "Starting Chatterbox TTS API..."
    shell.Run "cmd.exe /c ""C:\AI\chatterbox-api\_start.bat""", 0, False
    WScript.Sleep 3000
    ' Wait for Chatterbox to be ready — only when we just launched it
    WaitForChatterbox
Else
    ' Chatterbox already running — deduplicate: kill extras, keep one
    WriteLog "Chatterbox already running — checking for duplicate instances..."
    KillExtraChatterboxProcesses()
End If

' Launch WakeListener in visible console window (style=1 = normal) for monitoring
' Use python.exe (not pythonw) to enable console output during development
shell.Run """" & python & """ """ & script & """", 1, False
WScript.Sleep 500  ' Brief pause — shrinks race window if VBS is double-clicked rapidly

' Read the real PID from the lock file that run_wake_listener.py writes at startup.
' shell.Run(..., False) always returns 0 — it is not a PID.
Dim realPid, attempts, lf2, pidStr
realPid = 0
attempts = 0
Do While attempts < 20 And realPid = 0
    WScript.Sleep 250
    If fso.FileExists(lockPath) Then
        On Error Resume Next
        Set lf2 = fso.OpenTextFile(lockPath, 1)
        pidStr = Trim(lf2.ReadAll())
        lf2.Close
        On Error GoTo 0
        If IsNumeric(pidStr) And CLng(pidStr) > 0 Then
            realPid = CLng(pidStr)
        End If
    End If
    attempts = attempts + 1
Loop

' Log startup
WriteLog "WakeListener started PID: " & realPid

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
    Set processes = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name='python.exe' OR Name='pythonw.exe'")
    For Each process In processes
        If InStr(process.CommandLine, processName) > 0 Then
            count = count + 1
        End If
    Next
    On Error GoTo 0
    IsProcessRunning = (count > 0)
End Function

Function IsChatterboxRunning()
    Dim port, url, http
    For port = 4123 To 4129
        url = "http://127.0.0.1:" & port & "/health"
        On Error Resume Next
        Set http = CreateObject("MSXML2.XMLHTTP")
        http.Open "GET", url, False
        http.Send
        If http.Status = 200 Then
            Set http = Nothing
            IsChatterboxRunning = True
            Exit Function
        End If
        On Error GoTo 0
        Set http = Nothing
    Next
    IsChatterboxRunning = False
End Function

Sub WaitForChatterbox()
    Dim attempts, port, url, http

    For attempts = 1 To 24
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
        WScript.Sleep 5000
    Next
End Sub

Sub KillChatterboxProcesses()
    ' Kill ALL python.exe processes whose command line contains "chatterbox".
    ' Used when the disable flag file is present to guarantee a clean SAPI-only boot.
    Dim wmi, processes, proc, killed
    killed = 0
    On Error Resume Next
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    Set processes = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name='python.exe'")
    For Each proc In processes
        If InStr(LCase(proc.CommandLine), "chatterbox") > 0 Then
            proc.Terminate(0)
            WriteLog "Killed Chatterbox PID: " & proc.ProcessId
            killed = killed + 1
        End If
    Next
    On Error GoTo 0
    If killed > 0 Then
        WScript.Sleep 1500  ' Wait for ports to release after termination
    End If
End Sub

Sub KillExtraChatterboxProcesses()
    ' Deduplication: if more than one Chatterbox process is running, kill the extras.
    ' Keeps the lowest PID (first started), terminates all others.
    Dim wmi, processes, proc
    Dim pids(), count, i, j, tmp
    count = 0
    On Error Resume Next
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    Set processes = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name='python.exe'")

    ' Collect all Chatterbox PIDs
    ReDim pids(50)
    For Each proc In processes
        If InStr(LCase(proc.CommandLine), "chatterbox") > 0 Then
            pids(count) = proc.ProcessId
            count = count + 1
        End If
    Next
    On Error GoTo 0

    If count <= 1 Then Exit Sub  ' 0 or 1 instance — nothing to deduplicate

    ' Sort PIDs ascending (bubble sort — small list, doesn't matter)
    For i = 0 To count - 2
        For j = 0 To count - 2 - i
            If pids(j) > pids(j + 1) Then
                tmp = pids(j) : pids(j) = pids(j + 1) : pids(j + 1) = tmp
            End If
        Next
    Next

    ' Kill all but the first (lowest PID)
    WriteLog "Chatterbox dedup: " & count & " instances found, keeping PID " & pids(0)
    On Error Resume Next
    Set processes = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name='python.exe'")
    For Each proc In processes
        If InStr(LCase(proc.CommandLine), "chatterbox") > 0 Then
            If proc.ProcessId <> pids(0) Then
                proc.Terminate(0)
                WriteLog "Chatterbox dedup: killed extra PID " & proc.ProcessId
            End If
        End If
    Next
    On Error GoTo 0
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
