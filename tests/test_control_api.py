import os
import time
from unittest.mock import patch

from agent.control_api import app
from fastapi.testclient import TestClient


def _wait_for_plugin(client, plugin_id: str, timeout: float = 5.0) -> bool:
    """Poll /plugins until plugin_id appears or timeout expires — replaces fixed sleep (#106)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get("/plugins")
        if any(p.get("id") == plugin_id for p in resp.json().get("plugins", [])):
            return True
        time.sleep(0.05)
    return False


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

        # Poll until plugin appears — avoids fixed sleep (#106)
        assert _wait_for_plugin(client, "pkg.test"), "Plugin did not appear after install"

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
            # Poll until plugin appears — avoids fixed sleep (#106)
            _wait_for_plugin(client, "pkg.test")

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


# ---------------------------------------------------------------------------
# Finding #105 — API auth and CSRF endpoint verb tests
# ---------------------------------------------------------------------------


class TestAuthRequired:
    """API key middleware must reject unauthenticated requests when key is configured."""

    def test_missing_key_returns_401(self):
        """With ROAMIN_CONTROL_API_KEY set, request without key returns 401."""
        with patch.dict(os.environ, {"ROAMIN_CONTROL_API_KEY": "test-secret-key"}):
            with TestClient(app) as client:
                r = client.get("/status")
                assert r.status_code == 401

    def test_correct_key_accepted(self):
        """Correct x-roamin-api-key header passes authentication."""
        with patch.dict(os.environ, {"ROAMIN_CONTROL_API_KEY": "test-secret-key"}):
            with TestClient(app) as client:
                r = client.get("/status", headers={"x-roamin-api-key": "test-secret-key"})
                assert r.status_code == 200

    def test_wrong_key_returns_401(self):
        """Wrong key value returns 401."""
        with patch.dict(os.environ, {"ROAMIN_CONTROL_API_KEY": "test-secret-key"}):
            with TestClient(app) as client:
                r = client.get("/status", headers={"x-roamin-api-key": "wrong-key"})
                assert r.status_code == 401


class TestApprovalEndpointVerb:
    """Approve/deny endpoints must be POST-only — finding #86 CSRF regression."""

    def test_approve_get_returns_405(self):
        """GET /approve/{id} must return 405 after POST-only fix."""
        with TestClient(app) as client:
            r = client.get("/approve/1")
            assert r.status_code == 405

    def test_deny_get_returns_405(self):
        """GET /deny/{id} must return 405 after POST-only fix."""
        with TestClient(app) as client:
            r = client.get("/deny/1")
            assert r.status_code == 405

    def test_approve_post_not_405(self):
        """POST /approve/{id} is the correct verb — must not return 405."""
        with TestClient(app) as client:
            r = client.post("/approve/9999")
            # 404 = approval not found (correct); anything but 405 confirms verb is accepted
            assert r.status_code != 405

    def test_deny_post_not_405(self):
        """POST /deny/{id} is the correct verb — must not return 405."""
        with TestClient(app) as client:
            r = client.post("/deny/9999")
            assert r.status_code != 405
