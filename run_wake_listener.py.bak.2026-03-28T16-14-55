"""Startup entry point for WakeListener — run this to start ctrl+space."""

import keyboard  # noqa: F401 - validates keyboard is available before blocking

from agent.core.voice.wake_listener import WakeListener

listener = WakeListener(hotkey="ctrl+space")
listener.start()

# Block forever — keyboard module handles events in background
keyboard.wait()
