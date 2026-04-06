# Proposal: User Experience Enhancements (Priority 6)

## Why

Phases 1-4 delivered a stable, robust agent pipeline. Priority 5 added the Control API and SPA.
The agent works end-to-end but has three UX gaps that hurt daily usability:

1. **Dead silence during execution** — Between the wake greeting and the final spoken reply,
   the user hears nothing for 5-30+ seconds. No indication whether the agent is planning,
   searching, or stuck.

2. **Legacy modal notifications** — `_notify_windows()` uses `WScript.Shell.Popup()` which
   creates a blocking modal dialog. Not modern, not non-blocking, not Windows 10/11 native.

3. **No persistent task history** — AgentLoop stores only a one-line summary in `actions_taken`
   (goal + step count). Individual step details (tool, params, outcome, duration) are discarded.
   Cannot query past tasks by date, status, or keyword.

## What Changes

- `screen_observer.py` gains **modern toast notifications**: `_notify_windows()` replaced with
  `winotify` (non-blocking Windows 10/11 native toasts). Falls back to existing WScript.Shell
  if winotify is unavailable.

- `agent_loop.py` gains **progress callbacks**: `run()` accepts an optional `on_progress`
  callable. Emits events at planning, step_start, step_done phases. The caller (wake_listener)
  decides whether to speak a TTS cue or broadcast a WS event.

- `memory_store.py` gains **persistent task history**: Two new SQLite tables (`task_runs`,
  `task_steps`) store full step-level detail. Query methods support filtering by date, status,
  and keyword search.

- `control_api.py` `/task-history` endpoint updated to query persistent SQLite data with
  optional filters.

## Capabilities

- `toast-notifications` — non-blocking Windows 10/11 native toasts with fallback
- `task-progress` — real-time spoken/WS progress updates during AgentLoop execution
- `task-history` — persistent step-level task logging with query support

## Skipped Items

- **6.4 RoaminCP UI Integration** — Control API + SPA already exist; low daily-use value
- **6.5 Cancel Hotkey** — Already implemented and archived (2026-04-04)

## Impact

**Files modified:**
- `agent/core/screen_observer.py`
- `agent/core/tools.py`
- `agent/core/agent_loop.py`
- `agent/core/voice/wake_listener.py`
- `agent/core/voice/tts.py`
- `agent/core/memory/memory_store.py`
- `agent/core/memory/memory_manager.py`
- `agent/control_api.py`

**New dependency:** `winotify>=1.1.0` (pure Python, MIT, no C extensions)

**No breaking changes** to any public API. Progress callback is optional (default None).
