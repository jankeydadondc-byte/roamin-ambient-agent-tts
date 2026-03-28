Option Explicit

Dim shell, fso, pythonw, script, workingDir, logFile, pid

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Paths (all in NEW repo)
pythonw = "C:\AI\roamin-ambient-agent-tts\.venv\Scripts\pythonw.exe"
script = "C:\AI\roamin-ambient-agent-tts\run_wake_listener.py"
workingDir = "C:\AI\roamin-ambient-agent-tts"
logFile = "C:\AI\roamin-ambient-agent-tts\logs\startup.log"

' Single-instance guard: check if run_wake_listener is already running
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

Function IsProcessRunning(processName)
    Dim tempFile, wmiQuery, output, count
    tempFile = shell.ExpandEnvironmentStrings("%TEMP%\") & "roamin_wake_check_" & Replace(Replace(Replace(Now(), "/", "-"), ":", "-"), " ", "_") & ".txt"

    ' WMI query to find pythonw processes with run_wake_listener in CommandLine
    wmiQuery = "SELECT * FROM Win32_Process WHERE Name='pythonw.exe' AND CommandLine LIKE '%run_wake_listener%'"

    ' Save WMI output to temp file using PowerShell
    Dim psCommand
    psCommand = "Get-WmiObject -Query """ & wmiQuery & """ | Select-Object ProcessId,CommandLine | Out-File -FilePath """ & tempFile & """"
    shell.Run "powershell -Command " & Chr(34) & psCommand & Chr(34), 0, True

    ' Check if file has any entries
    If fso.FileExists(tempFile) Then
        output = ReadFile(tempFile)
        count = CountLines(output)
        fso.DeleteFile tempFile, True

        IsProcessRunning = (count > 0)
    Else
        IsProcessRunning = False
    End If
End Function

Sub WaitForChatterbox()
    Dim attempts, port, url, shellObj, http, status

    Set shellObj = CreateObject("WScript.Shell")

    ' Poll up to 20 times (60 seconds total)
    For attempts = 1 To 20
        ' Try each port in range 4123-4129
        For port = 4123 To 4129
            url = "http://127.0.0.1:" & port & "/health"

            On Error Resume Next
            Set http = CreateObject("MSXML2.XMLHTTP")
            http.Open "GET", url, False
            http.Send

            If http.Status = 200 Then
                ' Chatterbox is up — we can continue
                Set http = Nothing
                Exit Sub
            End If

            On Error GoTo 0
        Next

        WScript.Sleep 3000 ' Wait 3 seconds before next poll
    Next

    ' If we get here, Chatterbox didn't come up — continue anyway (TTS fallback available)
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

Function ReadFile(filePath)
    Dim f
    If fso.FileExists(filePath) Then
        Set f = fso.OpenTextFile(filePath, 1)
        ReadFile = f.ReadAll
        f.Close
    Else
        ReadFile = ""
    End If
End Function

Function CountLines(text)
    Dim trimmed
    trimmed = Trim(text)
    If trimmed = "" Then
        CountLines = 0
    Else
        CountLines = UBound(Split(trimmed, vbCrLf)) + 1
    End If
End Function
