"""Convenience runner for the Control API (development).

Run with:

    python run_control_api.py

This assumes `fastapi` and `uvicorn` are installed in the active environment.
"""

from __future__ import annotations

import os

import uvicorn

from agent.core import ports


def main() -> None:
    port = int(os.environ.get("ROAMIN_CONTROL_API_PORT") or ports.CONTROL_API_DEFAULT_PORT)
    uvicorn.run("agent.control_api:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
