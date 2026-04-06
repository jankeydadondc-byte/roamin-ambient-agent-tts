# Design: User Experience Enhancements

## Context

The agent pipeline is stable: wake → STT → classify → plan → execute → TTS. Cancel hotkey
works. Tools have fallback chains. But the user experience during execution is silent, and
past task details are lost after each run.

## Goals

- Replace legacy modal notifications with non-blocking Windows 10/11 toasts
- Provide spoken and terminal progress cues during AgentLoop execution
- Persist full step-level task history in SQLite for querying

## Non-Goals

- System tray icon (separate scope)
- Cross-platform notification support (Windows-only tool)
- Real-time progress for individual tool execution (only between-step updates)
- Async/await refactor of the execution pipeline

## Decisions

**D1 — winotify for toast notifications**

Use `winotify` (pure Python, MIT) for Windows 10/11 native toasts. It calls the Windows
Runtime notification API directly, is non-blocking, auto-dismisses, and supports app branding.

*Alternatives rejected:*
- `windows-toasts` — heavier, more features than needed for simple notifications
- `plyer` — cross-platform but weaker Windows support
- PowerShell `BurntToast` — requires separate PS module installation
- Keep WScript.Shell — modal, blocking, XP-era appearance

**Fallback preserved:** If `winotify` is not importable, the existing WScript.Shell code runs.

**D2 — Plain callback for progress, not pub/sub**

`on_progress: Callable[[dict], None] | None` parameter on `AgentLoop.run()`. The caller
(wake_listener `_on_wake`) passes a closure that speaks TTS cues and/or broadcasts WS events.

*Rationale:* Exactly one producer (AgentLoop) and one consumer (wake handler). A callback is
the right tool for a 1:1 relationship. No event bus, no pub/sub, no extra abstraction.

*Alternative rejected:* Global event bus — adds complexity for a single-developer tool with
exactly one consumer.

**D3 — Progress phrases in TTS cache**

"Let me think..." is added to the pre-synthesized phrase cache. Playback is instant (no
Chatterbox synthesis delay). Step announcements like "Step 2 of 4" are synthesized live
via pyttsx3 (fast enough for short phrases).

**D4 — Step announcements only for 3+ step plans**

1-2 step plans complete in <5 seconds. Announcing steps would feel more intrusive than helpful.
Only plans with 3+ steps announce "Step N of M".

**D5 — New SQLite tables, not a new database**

`task_runs` and `task_steps` tables added to the existing `roamin_memory.db` via
`CREATE TABLE IF NOT EXISTS`. No migration framework needed. No new database file.

*Alternative rejected:* Separate `task_history.db` — adds file management overhead for no
benefit. The existing MemoryStore already handles SQLite connections and initialization.

**D6 — Logging failures never abort task execution**

All task history writes are wrapped in `try/except`. If SQLite is locked, disk full, or the
schema is corrupted, the task still executes normally. History is observability, not control flow.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| winotify may not work on older Windows builds | Fallback to WScript.Shell preserved |
| "Let me think..." delays task start by ~200ms | Phrase is pre-cached; playback is near-instant |
| Step announcements overlap with TTS reply | speak() is synchronous; each completes before next |
| SQLite writes add latency per step | ~1ms per INSERT; negligible vs 30s tool timeout |
| task_steps table grows unbounded | Future: add pruning by age; not urgent for personal use |

## Migration Plan

All changes are additive:
- `_notify_windows()` gains an optional `title` param — backward compatible
- `AgentLoop.run()` gains `on_progress` param with default `None` — no callers affected
- New SQLite tables auto-created — no existing data modified
- Existing `actions_taken` write preserved for backward compatibility
