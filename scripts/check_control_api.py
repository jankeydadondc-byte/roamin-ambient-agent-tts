#!/usr/bin/env python3
"""
Simple check for Control API endpoints used by the SPA.
Prints JSON responses for /status and /plugins.
"""
import json
import urllib.request

ENDPOINT = "http://127.0.0.1:8765"

for path in ("/status", "/plugins"):
    url = ENDPOINT + path
    try:
        with urllib.request.urlopen(url, timeout=5) as f:
            data = f.read().decode("utf-8")
            print(f"GET {path} -> {f.status}")
            try:
                print(json.dumps(json.loads(data), indent=2))
            except Exception:
                print(data)
    except Exception as e:
        print(f"GET {path} -> ERROR: {e}")
