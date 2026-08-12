"""Tests for authentication, authorization and role-based access."""
from starlette.testclient import TestClient


class TestLogin:
    def test_login_success_returns_token(self, client: TestClient):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["token_type"] == "bearer"
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password(self, client: TestClient):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_unknown_user(self, client: TestClient):
        resp = client.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "nobody123"},
        )
        assert resp.status_code == 401

    def test_me_returns_current_user(self, client: TestClient):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"


class TestRoleProtection:
    def test_endpoint_requires_auth(self):
        from starlette.testclient import TestClient

        from app.main import app as fastapi_app

        with TestClient(fastapi_app) as anon:
            resp = anon.get("/api/projects")
            assert resp.status_code == 401

    def test_viewer_cannot_create_project(self, viewer_client: TestClient):
        resp = viewer_client.post(
            "/api/projects",
            json={
                "name": "閲覧者作成試行",
                "branch": "本社",
                "work_type": "その他",
                "start_date": "2026-01-01",
                "end_date": "2026-03-31",
            },
        )
        assert resp.status_code == 403

    def test_viewer_can_read_projects(self, viewer_client: TestClient):
        resp = viewer_client.get("/api/projects")
        assert resp.status_code == 200

    def test_site_cannot_approve_activity(self, site_client: TestClient):
        resp = site_client.put(
            "/api/activities/some-id/approve",
            json={"approved": True},
        )
        assert resp.status_code == 403

    def test_site_cannot_manage_factors(self, site_client: TestClient):
        resp = site_client.post(
            "/api/factors",
            json={
                "category": "fuel",
                "item_name": "軽油",
                "unit": "L",
                "factor_value": 2.58,
                "effective_from": "2026-01-01",
                "source": "test",
            },
        )
        assert resp.status_code == 403

    def test_admin_can_manage_users(self, client: TestClient):
        resp = client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "newpass123",
                "display_name": "新規ユーザー",
                "role": "site",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "site"

    def test_duplicate_username_rejected(self, client: TestClient):
        resp = client.post(
            "/api/users",
            json={"username": "admin", "password": "admin12345", "role": "viewer"},
        )
        assert resp.status_code == 400

    def test_invalid_role_rejected(self, client: TestClient):
        resp = client.post(
            "/api/users",
            json={"username": "badrole", "password": "pass123456", "role": "superadmin"},
        )
        assert resp.status_code == 400
