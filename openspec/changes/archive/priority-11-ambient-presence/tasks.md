# Tasks — Priority 11: Ambient Presence

## Status

ALL MILESTONES ✅ COMPLETE. 149 tests passing, 0 regressions.

---

## 11.6 — Conversation Continuity (FOUNDATION — build first) ✅ COMPLETE

**Files:** `agent/core/voice/session.py` (CREATE), `agent/core/voice/wake_listener.py` (MODIFY),
`agent/control_api.py` (MODIFY), `tests/unit/test_session.py` (CREATE)

- [x] Create `SessionTranscript` class with ring buffer (last 10 exchanges)
- [x] `add(role, text)` — append user/assistant messages
- [x] `get_context_block()` — formatted string for prompt injection
- [x] Auto-new-session after 30 minutes of inactivity
- [x] "New conversation" voice command resets session
- [x] Persist exchanges to SQLite `conversation_history` table
- [x] Wire into wake_listener: add user transcript + Roamin response after each exchange
- [x] Wire into ContextBuilder/AgentLoop: inject session context before planning
- [x] Add `GET /chat/history` endpoint to control_api.py
- [x] Add `POST /chat` endpoint to control_api.py (text-based chat, bypasses STT)
- [x] Add `POST /chat/reset` endpoint to control_api.py
- [x] Tests: 18 tests (buffer overflow, session timeout, context format, persistence)

---

## 11.1 — Wake Word ("Hey Roamin") ✅ COMPLETE

**Files:** `agent/core/voice/wake_word.py` (CREATE), `run_wake_listener.py` (MODIFY),
`requirements.txt` (MODIFY), `tests/unit/test_wake_word.py` (CREATE)

- [x] Add `openwakeword` to requirements.txt
- [x] Create `models/wake_word/` directory (model training via Colab — manual step)
- [x] Create `WakeWordListener` class with background daemon thread
- [x] 80ms frame mic reading via `sounddevice` at 16kHz
- [x] Feed frames to `openwakeword.Model` loaded from ONNX
- [x] On detection (confidence > threshold): fire callback
- [x] Configurable threshold via `ROAMIN_WAKE_THRESHOLD` env var (default: 0.5)
- [x] Detection cooldown (2s) to prevent rapid re-triggers
- [x] `pause()` / `resume()` methods — pause during Whisper recording
- [x] Fallback to built-in models if custom model not yet trained
- [x] Wire into `run_wake_listener.py`: both triggers call same `_on_wake_thread()`
- [x] Tests: 18 tests (init, pause/resume, detection, cooldown, callbacks)

---

## 11.2 — TTS Stop Word ✅ COMPLETE

**Files:** `agent/core/voice/wake_word.py` (MODIFY), `tests/unit/test_wake_word.py` (MODIFY)

- [x] Add `start_stop_listening()` / `stop_stop_listening()` to `WakeWordListener`
- [x] Stop model runs ONLY during TTS playback (separate from wake model)
- [x] On stop detection: callback fires to kill TTS audio stream
- [x] Wake word listener pauses during TTS (to avoid "hey roamin" during speech)
- [x] Energy gate: suppress stop detection when speaker output exceeds RMS threshold
- [x] Tests: stop callback fires, energy gate suppresses loud frames, threshold gating

---

## 11.3a — System Tray (pystray) ✅ COMPLETE

**Files:** `agent/core/tray.py` (CREATE), `run_wake_listener.py` (MODIFY),
`tests/unit/test_tray.py` (CREATE)

- [x] Create `RoaminTray` class wrapping `pystray.Icon`
- [x] Generate icon images programmatically via Pillow (colored circles, no icon files)
- [x] Icon states: idle (grey), awake (blue), thinking (yellow), speaking (green),
  error (red), privacy_pause (purple)
- [x] `set_state(state: str)` — updates icon dynamically
- [x] `flash()` method for proactive notification pings
- [x] Right-click context menu:
  - Open Chat (stub until 11.3b)
  - Status line (non-clickable)
  - Screenshots enabled (toggle)
  - Proactive notifications (toggle)
  - Restart Roamin
  - Quit (clean shutdown)
- [x] Wire into `run_wake_listener.py`: start tray on background thread
- [x] Tests: 14 tests (icon generation, state transitions, menu callbacks)

---

## 11.4 — Passive Observation ✅ COMPLETE

**Files:** `agent/core/observation.py` (CREATE), `run_wake_listener.py` (MODIFY),
`requirements.txt` (MODIFY), `tests/unit/test_observation.py` (CREATE)

- [x] Add `pytesseract` to requirements.txt
- [x] Create `ObservationLoop` class — daemon thread, 30s interval
- [x] PIL.ImageGrab screenshot → OCR via pytesseract
- [x] Configurable interval via `ROAMIN_OBS_INTERVAL` env var
- [x] Privacy detection: window title (InPrivate/Incognito/Private Browsing)
- [x] Privacy detection: VPN adapters (TAP/WireGuard/OpenVPN/Mullvad/NordLynx/ProtonVPN)
- [x] Privacy detection: sensitive content keywords (banking, medical, API keys)
- [x] On privacy trigger: 40-minute screenshot pause (configurable)
- [x] Manual override: `set_manual_override(True/False/None)` for tray + chat UI
- [x] Importance scoring: HIGH (store screenshot + text), MEDIUM (text only), LOW (discard)
- [x] Screenshots stored to `observations/` dir with timestamps
- [x] OCR text persisted to SQLite `observations` table
- [x] Storage hygiene: auto-delete screenshots older than 7 days
- [x] Storage hygiene: cap `observations/` at 500MB, prune oldest
- [x] Wire into `run_wake_listener.py` + tray privacy_pause state
- [x] Tests: 26 tests (privacy, VPN, sensitive content, importance, pause, storage, lifecycle)

---

## 11.5 — Proactive Notifications ✅ COMPLETE

**Files:** `agent/core/proactive.py` (CREATE), `run_wake_listener.py` (MODIFY),
`tests/unit/test_proactive.py` (CREATE)

- [x] Create `ProactiveEngine` class with priority queue
- [x] `queue_notification(message, priority, source)` — add to queue
- [x] 3-step delivery flow: tray flash → winotify popup → TTS speaks
- [x] Cancel flow: cancelled notifications stored in `pending_chat_messages`
- [x] `get_pending_messages()` — returns + clears pending for chat overlay
- [x] Quiet mode: `is_in_meeting()` detects Zoom/Teams/Meet/Webex/Discord
- [x] During quiet mode: notifications stop at Step 1 (tray ping only)
- [x] Enable/disable toggle
- [x] Wire into `run_wake_listener.py` + tray proactive toggle
- [x] Tests: 20 tests (queue ordering, delivery flow, quiet mode, pending messages, lifecycle)

---

## 11.3b — Chat Overlay (Tauri) ✅ COMPLETE

**Files:** `ui/roamin-chat/` (CREATE entire Tauri app), `agent/control_api.py` (MODIFY)

### Tauri App Setup
- [x] Scaffold `ui/roamin-chat/` Tauri project
- [x] Configure `tauri.conf.json`: 400x600, floating, resizable, always-on-top
- [x] Minimal `main.rs` — window creation
- [x] `Cargo.toml` with tauri dependencies
- [x] `build.rs` for tauri-build

### React UI
- [x] `Chat.jsx` — conversation view + text input + send button + typing indicator
- [x] `VolumeControl.jsx` — TTS volume slider (0–100%)
- [x] Model selector dropdown (reads from `GET /models`)
- [x] Privacy toggle (screenshots enable/disable)
- [x] Pending notifications display (messages Roamin wanted to say)
- [x] `apiClient.js` — chat-focused API client (same pattern as control-panel)
- [x] Dark theme CSS with proper styling

### Control API Endpoints
- [x] `POST /chat` — text-based chat through AgentLoop
- [x] `GET /chat/history` — session conversation history
- [x] `POST /chat/reset` — start new session
- [x] `GET /chat/pending` — pending proactive notifications
- [x] `POST /settings/volume` — set TTS volume (0.0–1.0)
- [x] `GET /settings` — current settings object
- [x] `POST /settings/screenshots` — enable/disable screenshots

---

## Verification

```powershell
# Final regression check:
.venv\Scripts\python -m pytest tests/unit/ tests/test_control_api.py -q
# Result: 149 passed (53 existing + 96 new, 0 failed)

# Manual tests (post-restart):
# Say "hey roamin" → agent activates (requires trained ONNX model)
# Press ctrl+space → agent still activates (both work)
# Say "new conversation" → session resets
# Say "quiet" during TTS → speech stops (requires stop ONNX model)
# Open incognito window → tray turns purple, screenshots pause
# Right-click tray → Open Chat → type message → get response
# Wait for proactive trigger → tray flashes → popup → TTS speaks
```

---

## Environment Variables (New)

| Variable | Default | Purpose |
|---|---|---|
| `ROAMIN_WAKE_THRESHOLD` | `0.5` | OpenWakeWord detection confidence threshold |
| `ROAMIN_OBS_INTERVAL` | `30` | Seconds between screenshots |
| `ROAMIN_OBS_MAX_AGE_DAYS` | `7` | Days before screenshots auto-deleted |
| `ROAMIN_OBS_MAX_SIZE_MB` | `500` | Max observations directory size |
| `ROAMIN_PRIVACY_PAUSE_MIN` | `40` | Minutes to pause screenshots on privacy detection |
| `ROAMIN_SESSION_TIMEOUT_MIN` | `30` | Minutes of silence before new session |

## New Files Created

| File | Purpose |
|---|---|
| `agent/core/voice/session.py` | SessionTranscript ring buffer + persistence |
| `agent/core/voice/wake_word.py` | OpenWakeWord listener + stop word |
| `agent/core/tray.py` | pystray system tray icon |
| `agent/core/observation.py` | Passive screenshot + OCR observation loop |
| `agent/core/proactive.py` | Proactive notification engine |
| `ui/roamin-chat/` | Tauri chat overlay (React + Rust) |
| `tests/unit/test_session.py` | 18 tests |
| `tests/unit/test_wake_word.py` | 18 tests |
| `tests/unit/test_tray.py` | 14 tests |
| `tests/unit/test_observation.py` | 26 tests |
| `tests/unit/test_proactive.py` | 20 tests |
