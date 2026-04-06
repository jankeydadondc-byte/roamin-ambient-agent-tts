#!/usr/bin/env python3
import json
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8765"

payload = {
    "id": "pkg.smoke.auto",
    "name": "Smoke Auto Plugin",
    "manifest": {"id": "pkg.smoke.auto", "name": "Smoke Auto Plugin", "entrypoint": "run.py"},
}


def main():
    print("POST /plugins/install")
    req = Request(
        BASE + "/plugins/install",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        res = urlopen(req, timeout=5)
        data = json.load(res)
        print("install response:", data)
        task_id = data.get("task_id") or data.get("taskId") or data.get("id")
    except URLError as e:
        print("install request failed", e)
        raise

    print("Polling /task-history for task...")
    start = time.time()
    found = False
    while time.time() - start < 20:
        try:
            j = json.load(urlopen(BASE + "/task-history", timeout=5))
            tasks = j.get("tasks", [])
            for t in tasks:
                if task_id and (t.get("task_id") == task_id or t.get("id") == task_id):
                    print("found task by id:", t)
                    found = True
                    break
                if (
                    t.get("plugin") == "pkg.smoke.auto"
                    or t.get("plugin_id") == "pkg.smoke.auto"
                    or "pkg.smoke.auto" in json.dumps(t)
                ):
                    print("found task by plugin:", t)
                    found = True
                    break
        except Exception as e:
            print("poll error", e)
        if found:
            break
        time.sleep(1)

    print("Result:", "OK" if found else "NOT FOUND")
    if not found:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
