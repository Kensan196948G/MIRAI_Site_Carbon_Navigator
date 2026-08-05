"""Tests for production operations: health, security headers, rate limit, admin."""
from starlette.testclient import TestClient


class TestHealth:
    def test_liveness(self, client: TestClient):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["version"] == "2.0.0"

    def test_readiness(self, client: TestClient):
        resp = client.get("/api/health/ready")
        assert resp.status_code == 200
        assert resp.json()["db"] == "ok"


class TestSecurityHeaders:
    def test_headers_present(self, client: TestClient):
        resp = client.get("/")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert "cdn.jsdelivr.net" in resp.headers["content-security-policy"]
        assert resp.headers["referrer-policy"] == "same-origin"


class TestRateLimit:
    def test_rate_limit_enforced(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("MIRAI_RATE_LIMIT_PER_MIN", "3")
        from app.main import _rate_hits

        _rate_hits.clear()
        for _ in range(3):
            assert client.get("/api/health").status_code == 200
        assert client.get("/api/health").status_code == 429


class TestAdminOps:
    def test_admin_status(self, client: TestClient):
        resp = client.get("/api/admin/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "2.0.0"
        assert data["db"] == "ok"
        assert "projects" in data

    def test_notify_test_without_channels(self, client: TestClient):
        resp = client.post("/api/admin/notify-test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email_sent"] is False
        assert data["teams_sent"] is False

    def test_viewer_forbidden(self, viewer_client: TestClient):
        assert viewer_client.get("/api/admin/status").status_code == 403
