"""Convenience runner for the Control API (development).

Run with:

    python run_control_api.py

This assumes `fastapi` and `uvicorn` are installed in the active environment.
"""

from __future__ import annotations

import logging
import logging.handlers
import os

import uvicorn

from agent.core import paths, ports


def _setup_logging() -> None:
    """Configure logging to capture both uvicorn and app logs to file."""
    project_root = paths.get_project_root()
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "control_api.log"

    # Configure root logger with file handler
    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=3,
    )
    formatter = logging.Formatter("%(levelname)s:     %(message)s")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def main() -> None:
    _setup_logging()
    port = int(os.environ.get("ROAMIN_CONTROL_API_PORT") or ports.CONTROL_API_DEFAULT_PORT)
    uvicorn.run("agent.control_api:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
