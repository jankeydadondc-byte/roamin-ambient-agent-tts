"""Dynamic port discovery utilities for Roamin's three local services."""

from __future__ import annotations

import os
import socket

CONTROL_API_DEFAULT_PORT: int = 8765
CONTROL_API_PORT_RANGE: range = range(8765, 8776)
OLLAMA_DEFAULT_URL: str = "http://127.0.0.1:11434"


def _is_port_live(host: str, port: int) -> bool:
    """Check if a TCP port is accepting connections (connect_ex == 0)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex((host, port)) == 0
    except Exception:
        return False


def _find_first_live_port(host: str, port_range: range) -> int | None:
    """Scan port range and return first live port or None."""
    for port in port_range:
        if _is_port_live(host, port):
            return port
    return None


def get_control_api_url() -> str:
    """
    Get Control API base URL with dynamic discovery.

    Priority order:
    1. ROAMIN_CONTROL_API_URL env var (full URL)
    2. ROAMIN_CONTROL_API_PORT env var (port only, builds URL)
    3. First live port in range 8765-8775
    4. Fallback to http://127.0.0.1:8765
    """
    env_url = os.environ.get("ROAMIN_CONTROL_API_URL")
    if env_url:
        return env_url.strip()

    env_port = os.environ.get("ROAMIN_CONTROL_API_PORT")
    if env_port:
        try:
            port = int(env_port)
            if 1 <= port <= 65535:
                return f"http://127.0.0.1:{port}"
        except ValueError:
            pass

    port = _find_first_live_port("127.0.0.1", CONTROL_API_PORT_RANGE)
    if port is not None:
        return f"http://127.0.0.1:{port}"

    return f"http://127.0.0.1:{CONTROL_API_DEFAULT_PORT}"


def get_ollama_url() -> str:
    """
    Get Ollama base URL.

    Priority order:
    1. OLLAMA_HOST env var (used as-is if set)
    2. http://127.0.0.1:11434
    """
    env_url = os.environ.get("OLLAMA_HOST")
    if env_url:
        return env_url.strip()

    return OLLAMA_DEFAULT_URL
