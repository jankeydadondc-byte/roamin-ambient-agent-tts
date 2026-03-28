"""observation_scheduler.py — Periodic screen observation with notifications."""

import threading
import time
from datetime import datetime

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

try:
    import win32gui
except ImportError:
    win32gui = None

from agent.core.screen_observer import ScreenObserver, _notify_windows


class ObservationScheduler:
    """Schedule periodic screen observations with user notifications."""

    def __init__(self):
        self._thread = None
        self._running = False
        self._interval = 300  # Default: 5 minutes

    def _worker(self):
        """Background thread that periodically captures observations and notifies user."""
        while self._running:
            observer = ScreenObserver()
            result = observer.observe()

            # Determine notification message based on result
            if "description" in result:
                message = f"[{datetime.now().strftime('%H:%M')}] Observation: {result['description'][:80]}..."
            else:
                error_msg = result.get("error", "unknown error")
                message = f"[{datetime.now().strftime('%H:%M')}] Observation failed: {error_msg}"

            _notify_windows(message)
            time.sleep(self._interval)

    def start(self, interval_seconds: int = 300) -> None:
        """
        Start periodic observation in background thread.

        Args:
            interval_seconds: Time between captures (default: 300s / 5 minutes)
        """
        if self._running:
            return

        self._interval = interval_seconds
        self._running = True

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the observation scheduler."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)

    def observe_now(self) -> dict:
        """
        Perform a single observation immediately.

        Returns:
            Result dict from ScreenObserver.observe()
        """
        observer = ScreenObserver()
        return observer.observe()

    @property
    def is_running(self) -> bool:
        """Check if scheduler is currently running."""
        return self._running


if __name__ == "__main__":
    # Quick smoke test - just verify imports and initialization work
    sched = ObservationScheduler()
    print(f"Scheduler created, is_running: {sched.is_running}")
