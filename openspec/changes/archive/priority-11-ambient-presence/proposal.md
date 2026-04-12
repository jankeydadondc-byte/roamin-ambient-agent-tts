# Priority 11: Ambient Presence

**Status:** DRAFT
**Date:** 2026-04-10
**Scope:** Transform Roamin from a voice-activated tool into an always-on ambient
companion — always listening, always observing, always ready.

---

## Vision

Roamin today is a capable voice assistant that does things when asked. Roamin tomorrow
is an ambient presence on the machine: it listens for its name, watches what you're
doing, consolidates memories in the background, and speaks up when it has something
worth saying — all while respecting privacy boundaries.

This proposal delivers six subsystems that together create the ambient experience:

1. **Wake Word** — "hey roamin" via OpenWakeWord (alongside `ctrl+space`)
2. **TTS Stop Word** — interrupt Roamin mid-speech with voice commands
3. **System Tray + Chat Overlay** — floating text UI, icon states, volume control
4. **Passive Observation** — periodic screenshots, OCR, importance scoring, privacy detection
5. **Proactive Notifications** — tray ping → popup → speaks (with cancel flow)
6. **Conversation Continuity** — recent session context stitched into every interaction

---

## What Already Exists

| Component | Status | Location |
|---|---|---|
| Whisper STT | ✅ Working | `agent/core/voice/wake_listener.py` |
| Chatterbox TTS | ✅ Working | `agent/core/voice/` |
| `ctrl+space` hotkey | ✅ Working | `run_wake_listener.py` (keyboard hook) |
| MemPalace semantic memory | ✅ Working | `agent/plugins/mempalace.py` |
| SQLite conversation history | ✅ Working | `agent/core/memory/memory_store.py` |
| Control Panel (React SPA) | ✅ Working | `ui/control-panel/` |
| System prompt file | ✅ Created | `roamin ambient agent system prompt.txt` |
| pystray | ✅ In requirements | `requirements.txt` |
| Tauri + cargo-tauri | ✅ Installed | `C:\Users\Asherre Roamin\.cargo\bin\cargo-tauri.exe` |

---

## Milestone 11.1 — Wake Word ("Hey Roamin")

**Library:** OpenWakeWord (Apache 2.0 code, ONNX inference)
**Integration reference:** RealtimeSTT (`github.com/KoljaB/RealtimeSTT`, 9.6k stars, MIT)
**Effort:** MEDIUM (1–2 days)

### What It Does

A background thread continuously reads from the microphone via a lightweight ONNX model.
When confidence on "hey roamin" crosses the threshold, it fires the same STT pipeline
that `ctrl+space` currently triggers. Both triggers coexist — voice for hands-free,
hotkey for quiet environments.

### Architecture

```
┌─────────────────────────────────────────┐
│ Microphone Stream (always on)           │
│                                         │
│  ┌──────────────┐   ┌────────────────┐  │
│  │ OpenWakeWord │   │ keyboard hook  │  │
│  │ "hey roamin" │   │  ctrl+space    │  │
│  └──────┬───────┘   └───────┬────────┘  │
│         │                   │           │
│         └───────┬───────────┘           │
│                 ▼                       │
│        _on_wake_triggered()             │
│         → Whisper STT (5s listen)       │
│         → AgentLoop / direct dispatch   │
│         → TTS response                  │
└─────────────────────────────────────────┘
```

### Implementation

1. `pip install openwakeword` — add to `requirements.txt`
2. Train custom "hey roamin" model via Google Colab notebook (one-time, produces
   `hey_roamin.onnx` → checked into `models/wake_word/`)
3. New module: `agent/core/voice/wake_word.py`
   - `WakeWordListener` class — runs on a daemon thread
   - Reads mic in 80ms frames via `sounddevice`
   - Feeds frames to `openwakeword.Model`
   - On detection: calls a callback (same function `ctrl+space` calls)
   - Configurable threshold via env var `ROAMIN_WAKE_THRESHOLD` (default: 0.5)
4. Wire into `run_wake_listener.py`:
   - Start `WakeWordListener` alongside existing keyboard hook
   - Both call `_on_wake_triggered()` → existing STT pipeline
   - Keyboard hook remains — no removal

### Key Decisions

- **Audio sharing:** OpenWakeWord and Whisper share the mic but never simultaneously —
  wake word listens until triggered, then pauses while Whisper records. After Whisper
  finishes, wake word resumes.
- **CPU cost:** <1% on desktop hardware. OpenWakeWord is benchmarked at 15–20 models
  per Raspberry Pi 3 core.
- **False positives:** Tunable via threshold. Start at 0.5, adjust based on testing.

---

## Milestone 11.2 — TTS Stop Word

**Effort:** LOW (0.5 day)

### What It Does

While Roamin is speaking (TTS playback active), a secondary listener monitors for
stop phrases: "quiet", "shut up", "roamin quit", "stop". On detection, TTS playback
is killed immediately.

### Architecture

OpenWakeWord can run multiple models simultaneously. During TTS playback:
1. Wake word listener pauses (to avoid "hey roamin" triggering during speech)
2. Stop word listener activates — lightweight model for stop phrases
3. On stop phrase detection → kill TTS audio stream, log the cancellation
4. After TTS ends (naturally or cancelled) → stop word listener pauses, wake word resumes

### Implementation

1. Train a "stop/quiet" model via same Colab notebook → `models/wake_word/stop_roamin.onnx`
2. Add to `WakeWordListener`:
   - `start_stop_listening()` — called when TTS begins
   - `stop_stop_listening()` — called when TTS ends
   - On stop detection → callback to kill TTS playback
3. Wire into TTS pipeline:
   - Before `tts.speak()`: `wake_word.start_stop_listening()`
   - After speak completes or is cancelled: `wake_word.stop_stop_listening()`

### Echo Cancellation

The stop word listener runs on the mic while speakers are playing TTS audio. To avoid
the listener hearing Roamin's own voice:
- OpenWakeWord's neural model is trained on human speech patterns, not synthesized audio —
  false triggers from TTS output are rare
- If echo is a problem in practice: add a simple energy gate — suppress detection when
  speaker output level exceeds threshold (detectable via `sounddevice` output stream)

---

## Milestone 11.3 — System Tray + Chat Overlay

**Effort:** HIGH (3–5 days)

### System Tray (pystray)

A Python-side system tray icon managed by `pystray`. Runs on the main thread or a
dedicated thread alongside `run_wake_listener.py`.

**Icon states:**

| State | Icon | When |
|---|---|---|
| Idle | ⚪ Grey circle | Listening for wake word, nothing happening |
| Awake | 🔵 Blue circle | Wake word detected, listening for command |
| Thinking | 🟡 Yellow circle | AgentLoop planning/executing |
| Speaking | 🟢 Green circle | TTS playback active |
| Error | 🔴 Red circle | Component crashed or disconnected |
| Privacy pause | 🟣 Purple circle | Screenshots paused (privacy detection) |

**Right-click context menu:**

```
┌────────────────────────────────┐
│  Open Chat                     │
│  ─────────────────────         │
│  Status: Idle                  │
│  ─────────────────────         │
│  ☑ Screenshots enabled         │  ← manual override toggle
│  ☑ Proactive notifications     │
│  ─────────────────────         │
│  Restart Roamin                │
│  Quit                          │
└────────────────────────────────┘
```

**Implementation:**

1. New module: `agent/core/tray.py`
   - `RoaminTray` class — wraps `pystray.Icon`
   - `set_state(state: str)` → updates icon
   - `run()` — blocking, starts tray loop
   - Icon images: programmatically generated colored circles via `Pillow`
     (no external icon files needed)
2. Wire into `run_wake_listener.py`:
   - Start tray on a background thread
   - State transitions driven by existing events:
     - Wake detected → `tray.set_state("awake")`
     - STT started → stays "awake"
     - AgentLoop started → `tray.set_state("thinking")`
     - TTS started → `tray.set_state("speaking")`
     - Done → `tray.set_state("idle")`
   - Right-click menu items dispatch actions to wake listener

### Chat Overlay (Tauri)

A lightweight Tauri application wrapping a compact-mode React UI. Launched from the
tray's right-click menu ("Open Chat"). Ports from the os_agent project's existing
Tauri setup (`C:\AI\os_agent\ui\roamin-control\src-tauri\`).

**What it provides:**

- Text input field (send message to Roamin without voice)
- Scrollable conversation history (current session)
- Model selector dropdown (global default)
- Volume slider (TTS output volume)
- Manual screenshot privacy override toggle
- Compact, floating, always-on-top optional

**Architecture:**

```
ui/roamin-chat/                  ← New Tauri app
├── src-tauri/
│   ├── Cargo.toml               ← Rust dependencies (tauri, tauri-plugin-*)
│   ├── tauri.conf.json          ← Window config (small, floating, tray integration)
│   └── src/
│       └── main.rs              ← Tauri entry point (minimal — window + tray bridge)
├── src/
│   ├── main.jsx                 ← React entry point
│   ├── Chat.jsx                 ← Conversation view + text input
│   ├── VolumeControl.jsx        ← TTS volume slider
│   └── apiClient.js             ← Reuse from ui/control-panel (same Control API)
├── index.html
├── package.json
└── vite.config.ts
```

**Backend communication:** Same Control API at `http://127.0.0.1:8765`. New endpoints
needed:

- `POST /chat` — send text message (bypasses STT, goes straight to AgentLoop)
- `GET /chat/history` — recent session messages
- `POST /settings/volume` — set TTS volume (0.0–1.0)
- `GET /settings` — current settings (volume, model, privacy mode)

**Update mechanism hook:** `tauri.conf.json` includes an `updater` section with
endpoint URL left blank — ready to wire a real update server later.

---

## Milestone 11.4 — Passive Observation

**Effort:** MEDIUM (2–3 days)

### What It Does

Every 30 seconds while Roamin is running, the agent takes a screenshot, runs OCR to
extract text, and asks a lightweight model to score the content's importance. High-value
observations are stored in memory. Low-value ones are discarded. Privacy-sensitive
content triggers a 40-minute screenshot pause.

### Architecture

```
┌────────────────────────────────────────────────────┐
│ Observation Loop (daemon thread, 30s interval)     │
│                                                    │
│  1. Screenshot (PIL.ImageGrab)                     │
│  2. OCR (pytesseract or Windows OCR API)           │
│  3. Privacy check:                                 │
│     - Window title: "InPrivate" / "Incognito" /    │
│       "Private Browsing"                           │
│     - VPN adapter detected (psutil)                │
│     - Content analysis: model flags sensitive       │
│     → If any: pause 40 min, set tray to purple     │
│  4. Importance scoring (model call):               │
│     - HIGH: store screenshot + OCR text to memory  │
│     - MEDIUM: store OCR text only (discard image)  │
│     - LOW: discard entirely                        │
│  5. Emit WebSocket event (observation_logged)      │
└────────────────────────────────────────────────────┘
```

### Privacy Detection

**Automatic triggers (any one pauses screenshots for 40 minutes):**

| Signal | Detection Method |
|---|---|
| Browser incognito/private | Window title contains "InPrivate", "Incognito", "Private Browsing" |
| VPN active | `psutil.net_if_addrs()` detects TAP/WireGuard/OpenVPN/NordVPN adapter |
| Sensitive content | Model analyzes OCR text and flags it (banking, medical, NSFW keywords) |

**Manual overrides:**
- Toggle in system tray right-click menu ("Screenshots enabled" checkbox)
- Toggle in chat overlay UI
- Both override automatic detection (enable or disable regardless of auto-detection)

**After 40-minute pause:** Re-check privacy signals. If still detected, extend another
40 minutes. If clear, resume automatic screenshots and reset tray icon.

### Implementation

1. New module: `agent/core/observation.py`
   - `ObservationLoop` class — daemon thread with 30s interval
   - `capture()` → PIL screenshot + OCR
   - `check_privacy()` → window title + VPN + content analysis
   - `score_importance(ocr_text)` → model call → HIGH/MEDIUM/LOW
   - `pause(minutes=40)` / `resume()` / `is_paused` property
2. OCR engine:
   - Primary: `pytesseract` (cross-platform, free)
   - Fallback: Windows OCR API via `winocr` (better accuracy on Windows)
   - Add `pytesseract` to requirements.txt
3. Storage:
   - Important screenshots → `observations/` directory (timestamped PNGs)
   - OCR text → SQLite `observations` table (already exists in memory_store.py)
   - MemPalace auto-mine new observations periodically
4. Wire into `run_wake_listener.py`:
   - Start `ObservationLoop` on daemon thread
   - Expose pause/resume via tray menu and chat overlay
   - State changes notify tray (`tray.set_state("privacy_pause")`)

### Storage Hygiene

- Screenshots older than 7 days auto-deleted (configurable)
- OCR text retained indefinitely in SQLite (searchable via memory)
- `observations/` directory size capped at 500MB — oldest files pruned when exceeded

---

## Milestone 11.5 — Proactive Notifications

**Effort:** MEDIUM (1–2 days)

### What It Does

When Roamin has something to say unprompted — based on observation analysis, time-based
triggers, or background memory insights — it follows a three-step notification flow
that respects the user's attention.

### Notification Flow

```
Step 1: System tray ping
  └─ Tray icon briefly flashes / shows notification badge
  └─ No interruption — user may not even notice

Step 2: Monitor popup (3-second window)
  └─ Small toast/popup appears on screen:
     "Roamin has something to say"
     [Let him speak]  [Cancel]
  └─ If ignored for 3 seconds → proceed to Step 3
  └─ If "Cancel" clicked → skip TTS, paste to chat instead

Step 3: Roamin speaks (TTS)
  └─ TTS reads the proactive message aloud
  └─ Stop word listener active (user can say "quiet" to interrupt)
  └─ If cancelled in Step 2 → message pasted into chat overlay
     text history for next time user opens it
```

### Quiet Mode

When quiet mode is active (meeting detected via window title or sustained mic audio),
proactive notifications stop at Step 1 (tray ping only). Message is stored for the
chat overlay.

**Meeting detection signals:**
- Active window title matches: Zoom, Teams, Meet, Webex, Discord (voice channel)
- Mic detects sustained audio from another speaker (>10s continuous non-self audio)

### Trigger Sources

What causes Roamin to want to speak proactively:

| Trigger | Example | Priority |
|---|---|---|
| Observation insight | "You've been on Stack Overflow for 20 minutes — want me to search your codebase?" | HIGH |
| Time-based check-in | "It's been 3 hours — want a summary of what you've done?" | LOW |
| Memory consolidation result | "I noticed a pattern: you always search for X before doing Y" | MEDIUM |
| Background task completion | "That web search you asked for earlier has results" | HIGH |

### Implementation

1. New module: `agent/core/proactive.py`
   - `ProactiveEngine` class
   - `queue_notification(message, priority, source)` — add to notification queue
   - `process_queue()` — runs on interval, checks quiet mode, executes flow
   - Quiet mode check: `is_in_meeting()` → window title scan + mic analysis
2. Notification popup:
   - Windows: `winotify` (already in requirements) for native toast
   - Popup includes "Cancel" action button → handled via callback
   - 3-second timeout → auto-proceed to TTS
3. Chat paste fallback:
   - When TTS is cancelled → write message to a `pending_chat_messages` queue
   - Chat overlay reads queue on open → displays missed notifications
4. Wire into observation loop and memory consolidation:
   - Observation loop can trigger proactive notifications
   - Memory consolidation job can trigger proactive notifications
   - Both call `proactive.queue_notification()`

---

## Milestone 11.6 — Conversation Continuity

**Effort:** LOW (0.5–1 day)

### What It Does

Every interaction with Roamin includes the last N exchanges from the current session
as context. Roamin remembers what you just talked about without being asked.

### Architecture

The existing `ContextBuilder.build()` already accepts memory data. This milestone adds
a lightweight session transcript buffer:

1. `agent/core/voice/session.py` — new module
   - `SessionTranscript` class
   - Stores last 10 exchanges (user utterance + Roamin response) in memory
   - `add(role, text)` — append to ring buffer
   - `get_context_block()` → formatted string for injection into prompts
   - Persists to SQLite `conversation_history` table (already exists)
   - Auto-starts new session after 30 minutes of inactivity
2. Wire into `wake_listener.py`:
   - After STT: `session.add("user", transcript)`
   - After TTS response: `session.add("assistant", response)`
   - Before AgentLoop: inject `session.get_context_block()` into context
3. Wire into chat overlay:
   - Text input → same `session.add()` path
   - Chat history view reads from `SessionTranscript`

### Session Boundaries

- New session auto-starts after 30 minutes of silence
- "Hey roamin, new conversation" → explicit session reset
- Session ID stored in SQLite for retrieval by MemPalace

---

## Dependencies & Requirements

### New Python Packages

```
openwakeword              # Wake word detection (Apache 2.0)
pytesseract               # OCR for passive observation
pystray>=0.19.0           # System tray (already added)
```

### New Node.js/Rust Packages (Tauri chat overlay)

```
@tauri-apps/api           # Tauri frontend API
@tauri-apps/cli           # Tauri build CLI
tauri                     # Rust crate
tauri-plugin-notification # Native notifications
```

### Model Files (checked into repo)

```
models/wake_word/
├── hey_roamin.onnx       # Custom wake word model (trained via Colab)
└── stop_roamin.onnx      # Stop word model (trained via Colab)
```

### New Control API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/chat` | POST | Send text message (bypasses STT) |
| `/chat/history` | GET | Recent session messages |
| `/settings` | GET | Current settings (volume, model, privacy, screenshots) |
| `/settings/volume` | POST | Set TTS volume |
| `/settings/screenshots` | POST | Enable/disable/pause screenshots |

---

## Files Created / Modified

### New Files

| File | Purpose |
|---|---|
| `agent/core/voice/wake_word.py` | OpenWakeWord listener (wake + stop) |
| `agent/core/voice/session.py` | Session transcript buffer |
| `agent/core/observation.py` | Passive observation loop (screenshot, OCR, privacy) |
| `agent/core/proactive.py` | Proactive notification engine |
| `agent/core/tray.py` | System tray icon + menu (pystray) |
| `ui/roamin-chat/` | Tauri chat overlay application (new) |
| `models/wake_word/hey_roamin.onnx` | Wake word model file |
| `models/wake_word/stop_roamin.onnx` | Stop word model file |
| `tests/unit/test_wake_word.py` | Wake word unit tests |
| `tests/unit/test_observation.py` | Observation loop unit tests |
| `tests/unit/test_proactive.py` | Proactive notification unit tests |
| `tests/unit/test_session.py` | Session continuity unit tests |

### Modified Files

| File | Change |
|---|---|
| `run_wake_listener.py` | Start wake word, tray, observation threads |
| `agent/control_api.py` | Add /chat, /settings endpoints |
| `agent/core/voice/wake_listener.py` | Integrate session transcript + proactive triggers |
| `requirements.txt` | Add openwakeword, pytesseract |
| `roamin ambient agent system prompt.txt` | Already created (✅) |
| `agent/core/config.py` | Already updated (✅) |

---

## What This Explicitly Does NOT Include

- **Calendar integration** — deferred indefinitely per decision
- **Mobile companion** — out of scope (desktop only)
- **Auto-updater implementation** — hook coded in Tauri config, mechanism built later
- **Video recording** — screenshots only, no screen recording
- **Cloud sync** — all data stays local
- **Multi-user mode** — single user per installation

---

## Implementation Order

Build order is driven by dependencies:

```
11.6 Conversation Continuity    ← foundation, no deps, enables everything else
 │
 ▼
11.1 Wake Word                  ← next most impactful, independent
 │
 ▼
11.2 TTS Stop Word              ← depends on 11.1 (same OpenWakeWord infrastructure)
 │
 ▼
11.3a System Tray (pystray)     ← independent of Tauri, can ship early
 │
 ▼
11.4 Passive Observation        ← needs tray for state display + privacy toggle
 │
 ▼
11.5 Proactive Notifications    ← needs observation (trigger source) + tray (quiet mode)
 │
 ▼
11.3b Chat Overlay (Tauri)      ← last, most complex, needs all above working
```

**Estimated total effort:** 10–15 days across all milestones.

---

## Acceptance Criteria

- [ ] "Hey roamin" wakes the agent from any room position (within mic range)
- [ ] `ctrl+space` still works alongside wake word
- [ ] "Quiet" or "shut up" stops TTS mid-sentence
- [ ] System tray icon reflects current state (idle/awake/thinking/speaking/error/privacy)
- [ ] Right-click menu shows Open Chat, screenshot toggle, quit
- [ ] Chat overlay opens from tray, accepts text input, shows conversation
- [ ] Screenshots taken every 30s, OCR'd, importance-scored
- [ ] Incognito/VPN/sensitive content triggers 40-min screenshot pause
- [ ] Manual override works from both tray menu and chat overlay
- [ ] Proactive notification follows 3-step flow (tray → popup → speak)
- [ ] Cancel button pastes message to chat instead of speaking
- [ ] Quiet mode suppresses TTS when in meeting
- [ ] Roamin references recent conversation naturally ("earlier you said...")
- [ ] All existing 53 tests still pass
- [ ] New tests cover wake word, observation, proactive, and session modules

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| "Hey roamin" false positives | Tunable threshold + quick iteration on model training |
| Echo (TTS triggers stop word) | Energy gate during TTS; OpenWakeWord resilient to synthetic speech |
| Screenshot CPU load | PIL.ImageGrab is fast (<50ms); OCR is the bottleneck — run async |
| Privacy miss (incognito not detected) | Manual override always available; best-effort + fallback |
| Tauri build fails on user's machine | Rust toolchain already confirmed installed; os_agent Tauri builds work |
| 30s screenshot interval too aggressive | Configurable via env var `ROAMIN_OBS_INTERVAL` (default: 30) |
| Friends don't have GPU | Future: API fallback mode (out of scope for P11) |

---

## Friends Distribution Considerations

These are noted for awareness but NOT implemented in P11:

- **GPU fallback:** API mode for non-RTX friends (OpenAI/Anthropic endpoint)
- **One-click installer:** Tauri can produce `.msi` — future packaging work
- **Per-user wake word training:** Each friend trains their own voice model
- **Update mechanism:** Tauri updater endpoint wired but empty — future work

---

**This is the largest priority since Priority 5. It transforms Roamin from a tool you
invoke into something that lives on your machine.**
