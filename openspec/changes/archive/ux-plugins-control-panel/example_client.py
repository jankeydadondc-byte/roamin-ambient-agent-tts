#!/usr/bin/env python3
"""
Example Python client for Roamin Control API.

Usage:
    python example_client.py
"""

from __future__ import annotations

import asyncio
import json
import os

import aiohttp
import websockets


class RoaminControlClient:
    """Simple async client for Roamin Control API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8765"):
        self.base_url = base_url
        self.api_key = os.environ.get("ROAMIN_CONTROL_API_KEY")
        self.headers = {}
        if self.api_key:
            self.headers["x-roamin-api-key"] = self.api_key

    async def get_status(self) -> dict:
        """Fetch system status."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/status",
                headers=self.headers,
            ) as resp:
                return await resp.json()

    async def list_models(self) -> dict:
        """List available models."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/models",
                headers=self.headers,
            ) as resp:
                return await resp.json()

    async def list_plugins(self) -> dict:
        """List installed plugins."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/plugins",
                headers=self.headers,
            ) as resp:
                return await resp.json()

    async def install_plugin(self, source: str, value: str) -> dict:
        """
        Install a plugin from file or URL.

        Args:
            source: "file" or "url"
            value: path to file or HTTPS URL
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/plugins/install",
                json={"source": source, "value": value},
                headers=self.headers,
            ) as resp:
                return await resp.json()

    async def uninstall_plugin(self, plugin_id: str) -> dict:
        """Uninstall a plugin."""
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{self.base_url}/plugins/{plugin_id}",
                headers=self.headers,
            ) as resp:
                return await resp.json()

    async def plugin_action(self, plugin_id: str, action: str) -> dict:
        """
        Perform plugin action (enable, disable, restart).

        Args:
            plugin_id: Plugin identifier
            action: "enable", "disable", or "restart"
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/plugins/{plugin_id}/action",
                json={"action": action},
                headers=self.headers,
            ) as resp:
                return await resp.json()

    async def get_task_history(self, limit: int = 100, status: str | None = None) -> dict:
        """Get task history."""
        params = {"limit": limit}
        if status:
            params["status"] = status

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/task-history",
                params=params,
                headers=self.headers,
            ) as resp:
                return await resp.json()

    async def listen_events(self):
        """Connect to WebSocket event stream and print events."""
        ws_url = "ws://127.0.0.1:8765/ws/events"
        print(f"[*] Connecting to {ws_url}")

        async with websockets.connect(ws_url) as ws:
            print("[+] Connected! Listening for events...")
            try:
                async for message in ws:
                    event = json.loads(message)
                    print(f"[EVENT] {event.get('type')}: {event.get('data')}")
            except asyncio.CancelledError:
                print("\n[-] Disconnected")


async def main():
    """Demo: connect to API and run sample commands."""
    client = RoaminControlClient()

    try:
        # Get status
        print("[*] Fetching status...")
        status = await client.get_status()
        print(f"[+] Status: {json.dumps(status, indent=2)}")

        # List models
        print("\n[*] Fetching models...")
        models = await client.list_models()
        print(f"[+] Models: {json.dumps(models, indent=2)}")

        # List plugins
        print("\n[*] Fetching plugins...")
        plugins = await client.list_plugins()
        print(f"[+] Plugins: {json.dumps(plugins, indent=2)}")

        # Get task history
        print("\n[*] Fetching task history...")
        tasks = await client.get_task_history(limit=10)
        print(f"[+] Tasks: {json.dumps(tasks, indent=2)}")

        # Listen for events (run for 5 seconds as demo)
        print("\n[*] Listening for events (5s timeout)...")
        try:
            await asyncio.wait_for(client.listen_events(), timeout=5)
        except asyncio.TimeoutError:
            print("[*] Event listener timeout (expected)")

    except ConnectionRefusedError:
        print("[!] Could not connect to Control API. Is it running?")
        print(f"    Expected: {client.base_url}")


if __name__ == "__main__":
    asyncio.run(main())
