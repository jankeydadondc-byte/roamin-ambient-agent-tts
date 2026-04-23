"""Proactive notification engine — queues and delivers unsolicited messages.

Three-step delivery flow:
  1. System tray ping (icon flash)
  2. Monitor popup via winotify (3s timeout, Cancel button)
  3. If not cancelled: TTS speaks the notification

Quiet mode detection: suppresses TTS when the user is in a meeting
(Zoom/Teams/Meet/etc. active window or sustained mic audio).

Part of Priority 11.5 — Ambient Presence.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Meeting app window title patterns
_MEETING_APP_PATTERNS = [
    "zoom",
    "teams",
    "google meet",
    "webex",
    "discord",
    "slack huddle",
    "microsoft teams",
]


@dataclass(order=True)
class Notification:
    """A proactive notification queued for delivery."""

    priority: int  # Lower = higher priority (for PriorityQueue ordering)
    message: str = field(compare=False)
    source: str = field(compare=False, default="system")
    timestamp: float = field(compare=False, default_factory=time.time)
    delivered: bool = field(compare=False, default=False)
    cancelled: bool = field(compare=False, default=False)


class ProactiveEngine:
    """Manages proactive notification delivery with quiet mode awareness.

    Usage:
        engine = ProactiveEngine(
            tray=roamin_tray,
            tts=text_to_speech,
        )
        engine.start()
        engine.queue_notification("Hey bud, you've been at this for 3 hours.", priority=2)
    """

    def __init__(
        self,
        tray=None,
        tts=None,
        on_cancelled: Callable[[str], None] | None = None,
        process_interval: float = 10.0,
    ) -> None:
        self._tray = tray
        self._tts = tts
        self._on_cancelled = on_cancelled  # Called with message text when user cancels
        self._process_interval = process_interval

        self._queue: queue.PriorityQueue[Notification] = queue.PriorityQueue()
        self._pending_chat_messages: list[dict] = []
        self._pending_lock = threading.Lock()

        self._running = False
        self._enabled = True
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        logger.info("Proactive notifications %s", "enabled" if value else "disabled")

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def start(self) -> None:
        """Start the notification processing thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._process_loop,
            name="proactive-engine",
            daemon=True,
        )
        self._thread.start()
        logger.info("ProactiveEngine started (interval=%.1fs)", self._process_interval)

    def stop(self) -> None:
        """Stop the notification processing thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("ProactiveEngine stopped")

    def queue_notification(
        self,
        message: str,
        priority: int = 5,
        source: str = "system",
    ) -> None:
        """Add a notification to the delivery queue.

        Args:
            message: The notification text to deliver
            priority: 1 (highest) to 10 (lowest), default 5
            source: Where this notification came from (observation, timer, memory, task)
        """
        notif = Notification(priority=priority, message=message, source=source)
        self._queue.put(notif)
        logger.info("Notification queued (priority=%d, source=%s): %s", priority, source, message[:60])

    def get_pending_messages(self) -> list[dict]:
        """Return and clear pending chat messages (cancelled notifications).

        Used by the chat overlay to display messages Roamin wanted to say.
        """
        with self._pending_lock:
            messages = list(self._pending_chat_messages)
            self._pending_chat_messages.clear()
        return messages

    def is_in_meeting(self) -> bool:
        """Check if the user appears to be in a meeting.

        Checks:
          - Active window title matches known meeting apps
          - (Future: sustained mic audio detection)
        """
        return self._check_meeting_window()

    # ------------------------------------------------------------------
    # Processing loop
    # ------------------------------------------------------------------

    def _process_loop(self) -> None:
        """Main loop — check queue and deliver notifications."""
        while self._running:
            try:
                if not self._enabled:
                    time.sleep(self._process_interval)
                    continue

                if self._queue.empty():
                    time.sleep(self._process_interval)
                    continue

                # Get next notification
                try:
                    notif = self._queue.get_nowait()
                except queue.Empty:
                    time.sleep(self._process_interval)
                    continue

                # Deliver the notification
                self._deliver(notif)

            except Exception as e:
                logger.warning("ProactiveEngine error: %s", e)
                time.sleep(self._process_interval)

    def _deliver(self, notif: Notification) -> None:
        """Execute the 3-step delivery flow for a notification."""
        in_meeting = self.is_in_meeting()

        # Step 1: System tray ping (always)
        if self._tray:
            try:
                self._tray.flash()
            except Exception as e:
                logger.debug("Tray flash failed: %s", e)

        # If in meeting / quiet mode: stop at step 1, queue for chat
        if in_meeting:
            logger.info("Quiet mode (meeting) — notification queued for chat: %s", notif.message[:60])
            self._store_for_chat(notif)
            return

        # Step 2: Monitor popup (3s timeout with Cancel)
        cancelled = self._show_popup(notif.message)

        if cancelled:
            logger.info("Notification cancelled by user — stored for chat")
            notif.cancelled = True
            self._store_for_chat(notif)
            if self._on_cancelled:
                try:
                    self._on_cancelled(notif.message)
                except Exception:
                    pass
            return

        # Step 3: TTS speaks
        notif.delivered = True
        if self._tts and self._tts.is_available():
            try:
                self._tts.speak_streaming(notif.message)
            except Exception as e:
                logger.warning("TTS delivery failed: %s", e)
        logger.info("Notification delivered via TTS: %s", notif.message[:60])

    def _show_popup(self, message: str) -> bool:
        """Show a Windows toast notification. Returns True if user cancelled.

        Uses winotify for native Windows toast notifications.
        The toast auto-dismisses after 3 seconds.
        Since winotify doesn't support synchronous cancel detection,
        we show the toast and proceed after a brief delay.
        """
        try:
            from winotify import Notification as WinNotif

            toast = WinNotif(
                app_id="Roamin",
                title="Roamin has something to say",
                msg=message[:200],
                duration="short",  # ~5 seconds
            )
            toast.show()
            # Give user time to see and potentially dismiss
            time.sleep(3)
            # winotify toasts are fire-and-forget — can't detect cancel synchronously.
            # Return False (not cancelled) — user can use stop word during TTS instead.
            return False
        except ImportError:
            logger.debug("winotify not installed — skipping popup")
            return False
        except Exception as e:
            logger.debug("Popup failed: %s", e)
            return False

    def _store_for_chat(self, notif: Notification) -> None:
        """Store a notification for display in the chat overlay."""
        with self._pending_lock:
            self._pending_chat_messages.append(
                {
                    "message": notif.message,
                    "source": notif.source,
                    "priority": notif.priority,
                    "timestamp": notif.timestamp,
                    "cancelled": notif.cancelled,
                }
            )

    # ------------------------------------------------------------------
    # Meeting detection
    # ------------------------------------------------------------------

    def _check_meeting_window(self) -> bool:
        """Check if the active window title matches a meeting application."""
        try:
            import win32gui

            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd).lower()
            return any(pattern in title for pattern in _MEETING_APP_PATTERNS)
        except ImportError:
            return False
        except Exception as e:
            logger.debug("Meeting window check failed: %s", e)
            return False
