"""Startup entry point for WakeListener — run this to start ctrl+space."""

import atexit
import logging
import os
import signal
import sys
from pathlib import Path

import keyboard  # noqa: F401 - validates keyboard is available before blocking

from agent.core.voice.wake_listener import WakeListener

# Constants
LOCK_FILE = Path(__file__).parent / "logs" / "_wake_listener.lock"

logger = logging.getLogger(__name__)


def check_stale_lock(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def write_lock_file() -> None:
    """Write current PID to lock file and ensure logs directory exists."""
    LOCK_FILE.parent.mkdir(exist_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))


def remove_lock_file() -> None:
    """Remove the lock file on exit."""
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except OSError as e:
        logger.warning(f"Failed to remove lock file: {e}")


def handle_signal(signum: int, frame: object | None) -> None:
    """Handle SIGTERM/SIGINT signals for clean exit."""
    raise SystemExit(0)


def main() -> None:
    """Main entry point with single-instance guard and cleanup."""
    # Configure logging
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    # Check for existing lock file and valid PID
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            if check_stale_lock(pid):
                logger.warning("WakeListener is already running (PID: %s). Exiting.", pid)
                sys.exit(0)
        except ValueError:
            pass  # Invalid lock file content, overwrite it

    # Write new lock file
    write_lock_file()

    # Register cleanup handlers
    atexit.register(remove_lock_file)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, handle_signal)
        except (OSError, ValueError):
            pass  # Signal not supported on this platform

    # Start WakeListener
    listener = WakeListener(hotkey="ctrl+space")
    listener.start()

    # Block forever — keyboard module handles events in background
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
