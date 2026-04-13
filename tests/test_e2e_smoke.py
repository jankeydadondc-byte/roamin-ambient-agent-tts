import json
import os
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest

from agent.core.ports import get_control_api_url

# All tests in this file require a live Control API — skip in standard pytest runs (#99)
pytestmark = pytest.mark.integration

BASE = os.environ.get("CONTROL_API_URL") or get_control_api_url()


def wait_for_service(timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = urlopen(BASE + "/status", timeout=2)
            if r.getcode() == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def test_install_creates_task():
    assert wait_for_service(), f"Control API not available at {BASE}"

    payload = {
        "id": "pkg.e2e.test",
        "name": "E2E Test Plugin",
        "manifest": {"id": "pkg.e2e.test", "name": "E2E Test Plugin", "entrypoint": "run.py"},
    }

    req = Request(
        BASE + "/plugins/install",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        res = urlopen(req, timeout=10)
        data = json.load(res)
    except URLError as e:
        raise AssertionError(f"Install request failed: {e}")

    task_id = data.get("task_id") or data.get("taskId") or data.get("id")

    # poll task-history for the task
    start = time.time()
    found = False
    while time.time() - start < 30:
        try:
            j = json.load(urlopen(BASE + "/task-history", timeout=5))
            tasks = j.get("tasks", [])
            for t in tasks:
                if task_id and (t.get("task_id") == task_id or t.get("id") == task_id):
                    found = True
                    break
                if (
                    t.get("plugin") == "pkg.e2e.test"
                    or t.get("plugin_id") == "pkg.e2e.test"
                    or "pkg.e2e.test" in json.dumps(t)
                ):
                    found = True
                    break
        except Exception:
            pass
        if found:
            break
        time.sleep(1)

    assert found, "Install task not observed in /task-history"
