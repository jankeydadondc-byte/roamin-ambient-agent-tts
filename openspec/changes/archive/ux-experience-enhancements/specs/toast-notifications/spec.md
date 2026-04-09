# Spec: Toast Notifications

## Requirements

### R1 — Non-blocking Windows 10/11 toast notification
When `_notify_windows(message)` is called, a native Windows 10/11 toast notification appears
in the Action Center. The calling thread is not blocked.

### R2 — Auto-dismisses without user interaction
The toast notification disappears from the screen after the system default timeout (typically
5-7 seconds) without requiring the user to click or dismiss it.

### R3 — Fallback to WScript.Shell when winotify unavailable
If `winotify` is not installed or fails to import, `_notify_windows()` falls back to the
existing `WScript.Shell.Popup()` implementation without raising an exception.

### R4 — Notify tool passes title and message correctly
The `notify` tool in the tool registry calls `_notify_windows(message, title=title)` and
both fields appear correctly in the toast notification.

---

## Scenarios

### Scenario 1: Toast notification with winotify installed
```
GIVEN winotify is installed
WHEN _notify_windows("Task completed", title="Roamin") is called
THEN a Windows 10/11 toast notification appears with title "Roamin" and body "Task completed"
AND the calling thread returns immediately (non-blocking)
```

### Scenario 2: Fallback when winotify not installed
```
GIVEN winotify is NOT installed (ImportError on import)
WHEN _notify_windows("Task completed") is called
THEN the WScript.Shell.Popup() fallback is used
AND no exception is raised
```

### Scenario 3: Notify tool integration
```
GIVEN the tool registry has "notify" registered
WHEN execute("notify", {"title": "Test", "message": "Hello"}) is called
THEN _notify_windows is called with message="Hello" and title="Test"
AND the tool returns {"success": True, ...}
```

### Scenario 4: Empty message rejected
```
GIVEN the notify tool is called
WHEN params has message="" or message is missing
THEN the tool returns {"success": False, "error": "No message provided"}
AND _notify_windows is NOT called
```

### Scenario 5: Exception in notification does not propagate
```
GIVEN winotify.Notification.show() raises an unexpected exception
WHEN _notify_windows("message") is called
THEN the exception is caught silently
AND the function returns without error
```
