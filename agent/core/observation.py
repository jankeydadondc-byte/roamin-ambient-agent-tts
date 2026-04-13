"""Passive observation loop — periodic screenshots with OCR, privacy detection,
importance scoring, and storage hygiene.

Captures the screen every N seconds (default 30), runs OCR via pytesseract,
scores importance via a lightweight model call, and stores/discards accordingly.

Privacy detection pauses screenshots for 40 minutes when:
  - Active window title contains "InPrivate", "Incognito", "Private Browsing"
  - VPN adapter detected (TAP, WireGuard, OpenVPN, Mullvad)
  - Content analysis flags sensitive material

Part of Priority 11.4 — Ambient Presence.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

# Point pytesseract at the standard Windows install location if not on PATH
_TESSERACT_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
try:
    import pytesseract as _pyt

    if not shutil.which("tesseract") and os.path.exists(_TESSERACT_DEFAULT):
        _pyt.pytesseract.tesseract_cmd = _TESSERACT_DEFAULT
except ImportError:
    pass

logger = logging.getLogger(__name__)

# --- Defaults (overridable via env vars) ---
_DEFAULT_INTERVAL = int(os.environ.get("ROAMIN_OBS_INTERVAL", "30"))
_DEFAULT_MAX_AGE_DAYS = int(os.environ.get("ROAMIN_OBS_MAX_AGE_DAYS", "7"))
_DEFAULT_MAX_SIZE_MB = int(os.environ.get("ROAMIN_OBS_MAX_SIZE_MB", "500"))
_DEFAULT_PRIVACY_PAUSE_MIN = int(os.environ.get("ROAMIN_PRIVACY_PAUSE_MIN", "40"))

# Privacy keywords in window titles
_PRIVACY_WINDOW_KEYWORDS = [
    "inprivate",
    "incognito",
    "private browsing",
    "private window",
]

# VPN adapter name patterns
_VPN_ADAPTER_PATTERNS = [
    "tap",
    "tun",
    "wireguard",
    "wg",
    "openvpn",
    "mullvad",
    "nordlynx",
    "proton",
]

# Content keywords that suggest privacy-sensitive material
_SENSITIVE_CONTENT_KEYWORDS = [
    "bank",
    "banking",
    "account balance",
    "credit card",
    "medical",
    "diagnosis",
    "prescription",
    "health record",
    "password",
    "secret key",
    "api key",
    "access token",
    "social security",
    "ssn",
]


class ObservationLoop:
    """Daemon thread that periodically captures screenshots and runs OCR.

    Usage:
        loop = ObservationLoop(on_observation=my_callback)
        loop.start()
        # ... later ...
        loop.stop()
    """

    def __init__(
        self,
        interval_seconds: int = _DEFAULT_INTERVAL,
        max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
        max_size_mb: int = _DEFAULT_MAX_SIZE_MB,
        privacy_pause_minutes: int = _DEFAULT_PRIVACY_PAUSE_MIN,
        observations_dir: Path | str | None = None,
        db_path: str | None = None,
        on_observation: Callable[..., None] | None = None,
    ) -> None:
        self._interval = interval_seconds
        self._max_age_days = max_age_days
        self._max_size_mb = max_size_mb
        self._privacy_pause_seconds = privacy_pause_minutes * 60

        project_root = Path(__file__).resolve().parents[2]
        self._observations_dir = Path(observations_dir) if observations_dir else project_root / "observations"
        self._observations_dir.mkdir(parents=True, exist_ok=True)

        self._on_observation = on_observation
        self._db_path = db_path

        self._running = False
        self._paused = False
        self._manual_override: bool | None = None  # None = auto, True = forced on, False = forced off
        self._privacy_pause_until: float = 0
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Lazy-loaded
        self._memory_store = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_privacy_paused(self) -> bool:
        """True if screenshots are currently paused for privacy."""
        if self._manual_override is not None:
            return not self._manual_override
        return time.time() < self._privacy_pause_until

    def start(self) -> None:
        """Start the observation loop on a daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name="observation-loop",
            daemon=True,
        )
        self._thread.start()
        logger.info("ObservationLoop started (interval=%ds)", self._interval)

    def stop(self) -> None:
        """Stop the observation loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("ObservationLoop stopped")

    def set_manual_override(self, enabled: bool | None) -> None:
        """Manually override privacy detection.

        Args:
            enabled: True = force screenshots ON, False = force OFF, None = auto
        """
        with self._lock:
            self._manual_override = enabled
        state = "auto" if enabled is None else ("on" if enabled else "off")
        logger.info("Screenshot manual override set to: %s", state)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        """Main observation loop — runs on daemon thread."""
        while self._running:
            try:
                # Check privacy state
                if self.is_privacy_paused:
                    logger.debug("Screenshots paused (privacy)")
                    time.sleep(self._interval)
                    continue

                # Check for privacy triggers
                privacy_reason = self._detect_privacy()
                if privacy_reason:
                    logger.info(
                        "Privacy detected (%s) — pausing screenshots for %d min",
                        privacy_reason,
                        self._privacy_pause_seconds // 60,
                    )
                    self._privacy_pause_until = time.time() + self._privacy_pause_seconds
                    if self._on_observation:
                        self._on_observation({"type": "privacy_pause", "reason": privacy_reason})
                    time.sleep(self._interval)
                    continue

                # Capture + analyze
                self._capture_and_analyze()

                # Storage hygiene
                self._prune_old_screenshots()
                self._enforce_size_limit()

            except Exception as e:
                logger.warning("Observation loop error: %s", e)

            time.sleep(self._interval)

    # ------------------------------------------------------------------
    # Capture & Analysis
    # ------------------------------------------------------------------

    def _capture_and_analyze(self) -> None:
        """Capture screenshot, run OCR, score importance, store or discard."""
        try:
            from PIL import ImageGrab
        except ImportError:
            logger.debug("PIL.ImageGrab not available — skipping capture")
            return

        # Check window title / VPN BEFORE capture — avoids OCR'ing sensitive data (#69)
        pre_capture_reason = self._detect_privacy()
        if pre_capture_reason:
            logger.info("Privacy detected before capture (%s) — skipping screenshot", pre_capture_reason)
            self._privacy_pause_until = time.time() + self._privacy_pause_seconds
            if self._on_observation:
                self._on_observation({"type": "privacy_pause", "reason": pre_capture_reason})
            return

        # Capture screenshot
        try:
            screenshot = ImageGrab.grab()
        except Exception as e:
            logger.debug("Screenshot capture failed: %s", e)
            return

        # OCR
        ocr_text = self._run_ocr(screenshot)

        # Secondary check: OCR text may reveal sensitivity not visible in window title (#69)
        if self._has_sensitive_content(ocr_text):
            logger.info("Sensitive OCR content detected — triggering privacy pause")
            self._privacy_pause_until = time.time() + self._privacy_pause_seconds
            if self._on_observation:
                self._on_observation({"type": "privacy_pause", "reason": "sensitive_content"})
            return

        # Score importance
        importance = self._score_importance(ocr_text)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if importance == "HIGH":
            # Store screenshot + OCR text
            screenshot_path = self._observations_dir / f"obs_{timestamp}.png"
            screenshot.save(str(screenshot_path), "PNG")
            self._persist_observation(ocr_text, str(screenshot_path))
            logger.info("HIGH importance observation stored: %s", screenshot_path.name)

        elif importance == "MEDIUM":
            # Store OCR text only, discard screenshot
            self._persist_observation(ocr_text, None)
            logger.info("MEDIUM importance observation stored (text only)")

        else:
            # LOW — discard entirely
            logger.debug("LOW importance observation discarded")

        # Notify callback
        if self._on_observation:
            self._on_observation(
                {
                    "type": "observation_logged",
                    "importance": importance,
                    "text_length": len(ocr_text),
                    "timestamp": timestamp,
                }
            )

    def _run_ocr(self, image) -> str:
        """Run OCR on a PIL Image. Returns extracted text."""
        try:
            import pytesseract

            text = pytesseract.image_to_string(image)
            return text.strip()
        except ImportError:
            logger.debug("pytesseract not installed — OCR unavailable")
            return ""
        except Exception as e:
            logger.debug("OCR failed: %s", e)
            return ""

    def _score_importance(self, ocr_text: str) -> str:
        """Score the importance of OCR text. Returns HIGH, MEDIUM, or LOW.

        Uses heuristics for speed — a lightweight model call can be added later.
        """
        if not ocr_text or len(ocr_text.strip()) < 20:
            return "LOW"

        text_lower = ocr_text.lower()

        # High importance: code, errors, tasks, important content
        high_signals = [
            "error",
            "exception",
            "traceback",
            "failed",
            "todo",
            "important",
            "deadline",
            "urgent",
            "def ",
            "class ",
            "import ",
            "function",
        ]
        if any(signal in text_lower for signal in high_signals):
            return "HIGH"

        # Medium importance: reasonable amount of text content
        word_count = len(ocr_text.split())
        if word_count > 50:
            return "MEDIUM"

        # Low importance: minimal or uninteresting content
        return "LOW"

    # ------------------------------------------------------------------
    # Privacy Detection
    # ------------------------------------------------------------------

    def _detect_privacy(self) -> str | None:
        """Check for privacy-sensitive conditions. Returns reason string or None."""
        # Check window title
        title_reason = self._check_window_title()
        if title_reason:
            return title_reason

        # Check VPN
        vpn_reason = self._check_vpn()
        if vpn_reason:
            return vpn_reason

        return None

    def _check_window_title(self) -> str | None:
        """Check if the active window title suggests private browsing."""
        try:
            import win32gui

            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd).lower()
            for keyword in _PRIVACY_WINDOW_KEYWORDS:
                if keyword in title:
                    return f"window_title:{keyword}"
        except ImportError:
            pass
        except Exception as e:
            logger.debug("Window title check failed: %s", e)
        return None

    def _check_vpn(self) -> str | None:
        """Check if a VPN adapter is active."""
        try:
            import psutil

            addrs = psutil.net_if_addrs()
            for iface_name in addrs:
                name_lower = iface_name.lower()
                for pattern in _VPN_ADAPTER_PATTERNS:
                    if pattern in name_lower:
                        return f"vpn_adapter:{iface_name}"
        except ImportError:
            pass
        except Exception as e:
            logger.debug("VPN check failed: %s", e)
        return None

    def _has_sensitive_content(self, ocr_text: str) -> bool:
        """Check if OCR text contains privacy-sensitive content."""
        if not ocr_text:
            return False
        text_lower = ocr_text.lower()
        return any(keyword in text_lower for keyword in _SENSITIVE_CONTENT_KEYWORDS)

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def _persist_observation(self, ocr_text: str, screenshot_path: str | None) -> None:
        """Write observation to SQLite."""
        store = self._get_store()
        if store is None:
            return
        try:
            store.add_observation(ocr_text[:5000], screenshot_path)  # cap text length
        except Exception as e:
            logger.warning("Failed to persist observation: %s", e)

    def _prune_old_screenshots(self) -> None:
        """Delete screenshots older than max_age_days."""
        if self._max_age_days <= 0:
            return
        cutoff = time.time() - (self._max_age_days * 86400)
        try:
            for f in self._observations_dir.glob("obs_*.png"):
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    logger.debug("Pruned old screenshot: %s", f.name)
        except Exception as e:
            logger.debug("Screenshot pruning error: %s", e)

    def _enforce_size_limit(self) -> None:
        """If observations dir exceeds max_size_mb, delete oldest files."""
        if self._max_size_mb <= 0:
            return
        max_bytes = self._max_size_mb * 1024 * 1024
        try:
            files = sorted(
                self._observations_dir.glob("obs_*.png"),
                key=lambda f: f.stat().st_mtime,
            )
            total = sum(f.stat().st_size for f in files)
            while total > max_bytes and files:
                oldest = files.pop(0)
                total -= oldest.stat().st_size
                oldest.unlink()
                logger.debug("Pruned for size: %s", oldest.name)
        except Exception as e:
            logger.debug("Size enforcement error: %s", e)

    def _get_store(self):
        """Lazy-load MemoryStore."""
        if self._memory_store is None:
            try:
                from agent.core.memory.memory_store import MemoryStore

                self._memory_store = MemoryStore(db_path=self._db_path)
            except Exception as e:
                logger.warning("Could not init MemoryStore for observations: %s", e)
                return None
        return self._memory_store
