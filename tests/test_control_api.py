import time

from fastapi.testclient import TestClient

from agent.control_api import app


def test_status_endpoint():
    with TestClient(app) as client:
        r = client.get("/status")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"


def test_plugin_install_and_list():
    with TestClient(app) as client:
        r = client.get("/plugins")
        assert r.status_code == 200

        payload = {
            "id": "pkg.test",
            "name": "Test Plugin",
            "manifest": {"id": "pkg.test", "name": "Test Plugin", "entrypoint": "run.py"},
        }
        inst = client.post("/plugins/install", json=payload)
        assert inst.status_code == 202
        task_id = inst.json().get("task_id")
        assert task_id

        # allow background install simulation to complete
        time.sleep(1.4)

        r2 = client.get("/plugins")
        assert r2.status_code == 200
        plugins = r2.json().get("plugins", [])
        assert any(p.get("id") == "pkg.test" for p in plugins)


def test_plugin_enable_disable():
    with TestClient(app) as client:
        r = client.get("/plugins")
        plugins = r.json().get("plugins", [])
        if not any(p.get("id") == "pkg.test" for p in plugins):
            client.post(
                "/plugins/install",
                json={"id": "pkg.test", "name": "Test Plugin", "manifest": {"id": "pkg.test", "entrypoint": "run.py"}},
            )
            time.sleep(1.4)

        r2 = client.post("/plugins/pkg.test/action", json={"action": "disable"})
        assert r2.status_code == 200

        r3 = client.get("/plugins/pkg.test")
        assert r3.status_code == 200
        assert r3.json().get("enabled") is False

        r4 = client.post("/plugins/pkg.test/action", json={"action": "enable"})
        assert r4.status_code == 200
        r5 = client.get("/plugins/pkg.test")
        assert r5.status_code == 200
        assert r5.json().get("enabled") is True
