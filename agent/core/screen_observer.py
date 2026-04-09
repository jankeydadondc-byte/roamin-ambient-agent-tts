"""screen_observer.py — Captures screen, sends to vision model, stores observation."""

import base64
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

try:
    import win32gui
except ImportError:
    win32gui = None

from agent.core.memory import MemoryManager
from agent.core.model_router import ModelRouter


class ScreenObserver:
    def __init__(self):
        self._project_root = Path(__file__).resolve().parents[2]
        self._screenshot_dir = self._project_root / "workspace" / "screenshots"
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

        router = ModelRouter()
        self._endpoint = router.endpoint("vision")
        self._model_id = router.model_id("vision")
        self._memory = MemoryManager()

    def _capture_screen(self) -> Path | None:
        """Capture screen and save to screenshot directory."""
        if ImageGrab is None:
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self._screenshot_dir / f"screen_{timestamp}.png"

        img = ImageGrab.grab()
        img.save(path, "PNG")
        return path

    def _get_active_window_title(self) -> str:
        """Get title of currently active window."""
        if win32gui is None:
            return "unknown"

        try:
            foreground_window = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(foreground_window)
            return title or "unknown"
        except Exception:
            return "unknown"

    def _encode_image(self, image_path: Path) -> str:
        """Encode image to base64 for API."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _send_to_vision_api(self, base64_image: str) -> str | None:
        """Send image to vision model and get description."""
        import requests

        url = f"{self._endpoint}/v1/chat/completions"

        payload = {
            "model": self._model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe what you see in this screenshot briefly (max 2 sentences)"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                    ],
                }
            ],
            "max_tokens": 300,
        }

        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.ConnectionError:
            return None
        except Exception:
            return None

    def _store_observation(self, description: str, screenshot_path: Path | None) -> bool:
        """Store observation in memory via A1 MemoryManager."""
        try:
            self._memory.write_to_memory(
                "observation",
                {
                    "description": description,
                    "screenshot_path": str(screenshot_path) if screenshot_path else None,
                },
            )
            return True
        except Exception:
            return False

    def observe(self) -> dict:
        """
        Main entry point: capture screen, send to vision model, store result.

        Returns dict with timestamp, window_title, description, screenshot_path, stored (bool).
        If LM Studio is not running, returns error key instead of description.
        """
        timestamp = datetime.now().isoformat()
        window_title = self._get_active_window_title()

        # Capture screen
        screenshot_path = self._capture_screen()
        if screenshot_path is None:
            return {
                "timestamp": timestamp,
                "window_title": window_title,
                "error": "PIL.ImageGrab unavailable",
                "screenshot_path": None,
                "stored": False,
            }

        # Encode image
        base64_image = self._encode_image(screenshot_path)

        # Send to vision API
        description = self._send_to_vision_api(base64_image)

        if description is None:
            return {
                "timestamp": timestamp,
                "window_title": window_title,
                "error": "LM Studio connection failed",
                "screenshot_path": str(screenshot_path),
                "stored": False,
            }

        # Store in memory
        stored = self._store_observation(description, screenshot_path)

        return {
            "timestamp": timestamp,
            "window_title": window_title,
            "description": description,
            "screenshot_path": str(screenshot_path),
            "stored": stored,
        }


def _notify_windows(message: str, title: str = "Roamin") -> None:
    """Send Windows toast notification (non-blocking).

    Uses winotify for native Windows 10/11 toasts when available.
    Falls back to WScript.Shell.Popup() if winotify is not installed.
    """
    try:
        from winotify import Notification

        toast = Notification(app_id="Roamin", title=title, msg=message)
        toast.set_audio(audio=None, silent=True)
        toast.show()
        return
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: legacy WScript.Shell popup (blocking, modal)
    powershell_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$shell = New-Object -ComObject WScript.Shell
$shell.Popup("{message}", 0, "{title}", 0x40)
"""
    try:
        subprocess.run(
            ["powershell", "-Command", powershell_script],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def _notify_approval_toast(approval_id: int, action: str, tool: str | None, port: int) -> None:
    """Show an Approve/Deny notification for a blocked HIGH-risk tool.

    Tier 1: winotify toast with clickable Approve/Deny buttons.
    Tier 2: PowerShell popup showing the approve/deny URLs (used when winotify unavailable).
    Never fatal — exceptions at both tiers are silently swallowed.
    """
    label = f"{tool}: {action[:80]}" if tool else action[:80]
    base = f"http://127.0.0.1:{port}"

    # Tier 1: winotify native toast with action buttons
    try:
        from winotify import Notification

        toast = Notification(app_id="Roamin", title="Action needs approval", msg=label)
        toast.add_actions("Approve", f"{base}/approve/{approval_id}")
        toast.add_actions("Deny", f"{base}/deny/{approval_id}")
        toast.show()
        return
    except Exception:
        pass  # fall through to PowerShell fallback

    # Tier 2: PowerShell popup with approve/deny URLs (non-blocking)
    try:
        approve_url = f"{base}/approve/{approval_id}"
        deny_url = f"{base}/deny/{approval_id}"
        msg = f"Roamin needs approval to run: {label}\\n\\n" f"APPROVE: {approve_url}\\n" f"DENY:    {deny_url}"
        powershell_script = f"""
$shell = New-Object -ComObject WScript.Shell
$shell.Popup("{msg}", 60, "Roamin — Action Needs Approval", 0x40)
"""
        subprocess.Popen(
            ["powershell", "-Command", powershell_script],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass  # never fatal


class ObservationScheduler:
    def __init__(self):
        self._thread = None
        self._running = False
        self._interval = 300  # Default: 5 minutes

    def _worker(self):
        """Background thread that periodically captures observations."""
        while self._running:
            observer = ScreenObserver()
            result = observer.observe()

            if "description" in result:
                message = f"Observed: {result['description'][:80]}..."
            else:
                message = f"Observation failed: {result.get('error', 'unknown error')}"

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
    # Quick smoke test without LM Studio (will fail at API call but shouldn't crash)
    obs = ScreenObserver()
    print(f"Endpoint: {obs._endpoint}")
    print(f"Model ID: {obs._model_id}")
    print(f"Screenshot dir: {obs._screenshot_dir}")
