"""System tray icon — pystray integration for Roamin ambient presence.

Provides a system tray icon with dynamic state colors and a right-click
context menu for controlling Roamin. Icon images are generated
programmatically via Pillow (no external icon files needed).

Part of Priority 11.3a — Ambient Presence.

States:
  idle         — grey   (waiting for wake)
  awake        — blue   (listening / STT active)
  thinking     — yellow (model inference)
  speaking     — green  (TTS playback)
  error        — red    (something failed)
  privacy_pause — purple (screenshots paused for privacy)
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None  # type: ignore[assignment,misc]
    ImageDraw = None  # type: ignore[assignment,misc]

try:
    import pystray
    from pystray import Icon, Menu, MenuItem
except ImportError:
    pystray = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# State → RGB color mapping
_STATE_COLORS: dict[str, tuple[int, int, int]] = {
    "idle": (128, 128, 128),  # grey
    "awake": (30, 144, 255),  # dodger blue
    "thinking": (255, 200, 0),  # golden yellow
    "speaking": (50, 205, 50),  # lime green
    "error": (220, 50, 50),  # red
    "privacy_pause": (148, 103, 189),  # purple
}

# Icon size
_ICON_SIZE = 64


def _make_icon_image(color: tuple[int, int, int]) -> Image.Image:
    """Generate a circular icon image of the given color."""
    if Image is None:
        raise RuntimeError("Pillow is required for tray icons")
    img = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Draw filled circle with a slight margin
    margin = 4
    draw.ellipse(
        [margin, margin, _ICON_SIZE - margin, _ICON_SIZE - margin],
        fill=color + (255,),
        outline=(255, 255, 255, 180),
        width=2,
    )
    return img


class RoaminTray:
    """System tray icon with state management and context menu.

    Usage:
        tray = RoaminTray(
            on_open_chat=lambda: print("Open chat"),
            on_toggle_screenshots=lambda enabled: print(f"Screenshots: {enabled}"),
            on_toggle_proactive=lambda enabled: print(f"Proactive: {enabled}"),
            on_restart=lambda: print("Restart"),
            on_quit=lambda: print("Quit"),
        )
        tray.start()
        tray.set_state("awake")
        # ... later ...
        tray.stop()

    The tray runs on its own thread (pystray requirement on Windows).
    """

    def __init__(
        self,
        on_open_chat: Callable[[], None] | None = None,
        on_toggle_screenshots: Callable[[bool], None] | None = None,
        on_toggle_proactive: Callable[[bool], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        self._on_open_chat = on_open_chat
        self._on_toggle_screenshots = on_toggle_screenshots
        self._on_toggle_proactive = on_toggle_proactive
        self._on_restart = on_restart
        self._on_quit = on_quit

        self._state = "idle"
        self._screenshots_enabled = True
        self._proactive_enabled = True
        self._icon: pystray.Icon | None = None  # type: ignore[name-defined]
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Pre-generate all state icons
        self._icons: dict[str, Image.Image] = {}
        if Image is not None:
            for state_name, color in _STATE_COLORS.items():
                self._icons[state_name] = _make_icon_image(color)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    @property
    def screenshots_enabled(self) -> bool:
        return self._screenshots_enabled

    @property
    def proactive_enabled(self) -> bool:
        return self._proactive_enabled

    def start(self) -> bool:
        """Start the system tray icon on a background thread. Returns True on success."""
        if pystray is None:
            logger.warning("pystray not installed — system tray unavailable")
            return False
        if Image is None:
            logger.warning("Pillow not installed — system tray icons unavailable")
            return False

        try:
            self._icon = Icon(
                name="Roamin",
                icon=self._icons.get("idle", _make_icon_image(_STATE_COLORS["idle"])),
                title="Roamin — Idle",
                menu=self._build_menu(),
            )
            self._thread = threading.Thread(
                target=self._icon.run,
                name="roamin-tray",
                daemon=True,
            )
            self._thread.start()
            logger.info("System tray started")
            return True
        except Exception as e:
            logger.error("Failed to start system tray: %s", e)
            return False

    def stop(self) -> None:
        """Stop the system tray icon."""
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
        logger.info("System tray stopped")

    def set_state(self, state: str) -> None:
        """Update the tray icon to reflect a new state.

        Valid states: idle, awake, thinking, speaking, error, privacy_pause
        """
        if state not in _STATE_COLORS:
            logger.warning("Unknown tray state: %s", state)
            return

        with self._lock:
            self._state = state

        if self._icon is not None:
            try:
                icon_img = self._icons.get(state)
                if icon_img:
                    self._icon.icon = icon_img
                self._icon.title = f"Roamin — {state.replace('_', ' ').title()}"
            except Exception as e:
                logger.debug("Failed to update tray icon: %s", e)

    def flash(self, times: int = 3, interval: float = 0.3) -> None:
        """Flash the tray icon between current state and a highlight color.

        Used for proactive notification pings. Runs on a separate thread.
        """

        def _flash():
            current = self._state
            for _ in range(times):
                self.set_state("awake")
                threading.Event().wait(interval)
                self.set_state(current)
                threading.Event().wait(interval)

        threading.Thread(target=_flash, daemon=True, name="tray-flash").start()

    # ------------------------------------------------------------------
    # Menu building
    # ------------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:  # type: ignore[name-defined]
        """Build the right-click context menu."""
        return Menu(
            MenuItem("Open Chat", self._handle_open_chat),
            MenuItem(
                lambda _: f"Status: {self._state.replace('_', ' ').title()}",
                None,
                enabled=False,
            ),
            Menu.SEPARATOR,
            MenuItem(
                "Screenshots enabled",
                self._handle_toggle_screenshots,
                checked=lambda _: self._screenshots_enabled,
            ),
            MenuItem(
                "Proactive notifications",
                self._handle_toggle_proactive,
                checked=lambda _: self._proactive_enabled,
            ),
            Menu.SEPARATOR,
            MenuItem("Restart Roamin", self._handle_restart),
            MenuItem("Quit", self._handle_quit),
        )

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------

    def _handle_open_chat(self, icon=None, item=None) -> None:
        if self._on_open_chat:
            try:
                self._on_open_chat()
            except Exception as e:
                logger.error("Open chat callback error: %s", e)

    def _handle_toggle_screenshots(self, icon=None, item=None) -> None:
        self._screenshots_enabled = not self._screenshots_enabled
        logger.info("Screenshots %s", "enabled" if self._screenshots_enabled else "disabled")
        if self._on_toggle_screenshots:
            try:
                self._on_toggle_screenshots(self._screenshots_enabled)
            except Exception as e:
                logger.error("Toggle screenshots callback error: %s", e)

    def _handle_toggle_proactive(self, icon=None, item=None) -> None:
        self._proactive_enabled = not self._proactive_enabled
        logger.info("Proactive notifications %s", "enabled" if self._proactive_enabled else "disabled")
        if self._on_toggle_proactive:
            try:
                self._on_toggle_proactive(self._proactive_enabled)
            except Exception as e:
                logger.error("Toggle proactive callback error: %s", e)

    def _handle_restart(self, icon=None, item=None) -> None:
        if self._on_restart:
            try:
                self._on_restart()
            except Exception as e:
                logger.error("Restart callback error: %s", e)

    def _handle_quit(self, icon=None, item=None) -> None:
        self.stop()
        if self._on_quit:
            try:
                self._on_quit()
            except Exception as e:
                logger.error("Quit callback error: %s", e)
