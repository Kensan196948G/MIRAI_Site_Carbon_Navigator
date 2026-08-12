"""Tests for enterprise features: multi-stage approval, 2FA/OIDC,
AI assistant, offset credits, annual report."""
import time

import pyotp
import pytest
from starlette.testclient import TestClient

from tests.conftest import make_activity, make_emission_factor, make_project


class TestMultiStageApproval:
    def test_full_approval_flow(self, client_pair):
        admin, reviewer, site = client_pair
        project = make_project(admin, branch="東京支店")
        activity = make_activity(admin, project["project_id"])
        aid = activity["activity_id"]

        # site submits
        resp = site.put(f"/api/activities/{aid}/approval", json={"action": "submit"})
        assert resp.status_code == 200
        assert resp.json()["approval_status"] == "site_submitted"
        assert resp.json()["approved"] is False

        # reviewer approves branch
        resp = reviewer.put(f"/api/activities/{aid}/approval", json={"action": "approve_branch"})
        assert resp.status_code == 200
        assert resp.json()["approval_status"] == "branch_approved"

        # admin approves env
        resp = admin.put(f"/api/activities/{aid}/approval", json={"action": "approve_env"})
        assert resp.status_code == 200
        assert resp.json()["approval_status"] == "env_approved"
        assert resp.json()["approved"] is True
        assert resp.json()["approved_by"] == "admin"

    def test_invalid_transition_rejected(self, client_pair):
        admin, _, site = client_pair
        project = make_project(admin, branch="東京支店")
        activity = make_activity(admin, project["project_id"])
        # draft -> approve_env is not allowed
        resp = site.put(
            f"/api/activities/{activity['activity_id']}/approval",
            json={"action": "approve_env"},
        )
        assert resp.status_code in (400, 403)

    def test_reject_resets_to_draft(self, client_pair):
        admin, reviewer, site = client_pair
        project = make_project(admin, branch="東京支店")
        activity = make_activity(admin, project["project_id"])
        site.put(f"/api/activities/{activity['activity_id']}/approval", json={"action": "submit"})
        resp = reviewer.put(
            f"/api/activities/{activity['activity_id']}/approval",
            json={"action": "reject", "comment": "根拠を再確認してください"},
        )
        assert resp.status_code == 200
        assert resp.json()["approval_status"] == "draft"
        comments = admin.get(f"/api/activities/{activity['activity_id']}/comments").json()
        assert any("reject" in c["content"] for c in comments)

    def test_calculation_only_includes_env_approved(self, client_pair):
        admin, reviewer, site = client_pair
        project = make_project(admin)
        make_emission_factor(admin, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_emission_factor(admin, category="power", item_name="電力", unit="kWh", factor_value=0.434)
        a1 = make_activity(admin, project["project_id"], category="fuel", item_name="軽油",
                           quantity=100.0, unit="L")
        a2 = make_activity(admin, project["project_id"], category="power", item_name="電力",
                           quantity=1000.0, unit="kWh")
        # only a2 fully approved (direct env approve via admin)
        admin.put(f"/api/activities/{a1['activity_id']}/approval", json={"action": "submit"})
        reviewer.put(f"/api/activities/{a1['activity_id']}/approval", json={"action": "approve_branch"})
        admin.put(f"/api/activities/{a1['activity_id']}/approval", json={"action": "approve_env"})
        admin.put(f"/api/activities/{a2['activity_id']}/approve", json={"approved": True})
        resp = admin.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        assert resp.status_code == 200
        co2 = sum(r["co2_kg"] for r in resp.json())
        assert co2 == pytest.approx(258.0 + 434.0)


class TestTwoFactorAuth:
    def test_2fa_flow(self, client: TestClient):
        setup = client.post("/api/auth/2fa/setup")
        assert setup.status_code == 200
        secret = setup.json()["secret"]
        assert not setup.json()["already_enabled"]

        code = pyotp.TOTP(secret).now()
        verify = client.post("/api/auth/2fa/verify", json={"code": code})
        assert verify.status_code == 200
        assert verify.json()["is_2fa_enabled"] is True

        # login now requires 2FA
        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert login.status_code == 200
        assert login.json()["requires_2fa"] is True
        temp_token = login.json()["temp_token"]

        # wrong code rejected
        bad = client.post(
            "/api/auth/2fa/login",
            json={"temp_token": temp_token, "code": "000000"},
        )
        assert bad.status_code == 401

        good = client.post(
            "/api/auth/2fa/login",
            json={"temp_token": temp_token, "code": pyotp.TOTP(secret).now()},
        )
        assert good.status_code == 200
        assert good.json()["token_type"] == "bearer"

        # disable 2FA again (use the code)
        disable = client.post(
            "/api/auth/2fa/disable",
            json={"code": pyotp.TOTP(secret).now()},
        )
        assert disable.status_code == 200
        assert disable.json()["is_2fa_enabled"] is False


class TestOidc:
    def test_callback_provisions_user(self, client: TestClient, monkeypatch):
        import app.routers.auth as auth_router
        from app.services import oidc

        monkeypatch.setattr(oidc, "oidc_enabled", lambda: True)
        monkeypatch.setattr(
            oidc,
            "login_with_code",
            lambda code: {"sub": "oidc-sub-123", "email": "external@example.com", "name": "外部ユーザー"},
        )
        auth_router._oidc_states["test-state"] = time.time() + 600
        resp = client.get("/api/auth/oidc/callback?code=abc&state=test-state", follow_redirects=False)
        assert resp.status_code in (307, 200)
        users = client.get("/api/users").json()
        assert any(u["username"] == "external" for u in users)

    def test_oidc_disabled(self, client: TestClient):
        resp = client.get("/api/auth/oidc/login", follow_redirects=False)
        assert resp.status_code == 400


class TestAssistant:
    def test_suggestions_use_history(self, client: TestClient):
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_emission_factor(client, category="power", item_name="電力", unit="kWh", factor_value=0.434)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=500.0, unit="L", target_month="2026-05", approved=True)
        make_activity(client, project["project_id"], category="power", item_name="電力",
                      quantity=1000.0, unit="kWh", target_month="2026-05", approved=True)
        client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )

        # peer project with implemented fuel action
        peer = client.post(
            "/api/projects",
            json={
                "name": "同工種比較工事",
                "branch": "大阪支店",
                "work_type": "土木工事",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        ).json()
        client.post(
            "/api/actions",
            json={
                "project_id": peer["project_id"],
                "target_month": "2026-05",
                "category": "fuel",
                "suggestion": "待機時間削減",
                "status": "implemented",
                "actual_reduction_kg": 500.0,
            },
        )
        resp = client.get(
            f"/api/assistant/suggestions?project_id={project['project_id']}&target_month=2026-05"
        )
        assert resp.status_code == 200
        suggestions = resp.json()
        assert len(suggestions) >= 1
        fuel = next(s for s in suggestions if s["category"] == "fuel")
        assert "実績" in fuel["rationale"]
        assert fuel["estimated_reduction_kg"] == pytest.approx(500.0)


class TestOffsetCredits:
    def test_credit_lifecycle(self, client: TestClient):
        project = make_project(client)
        c1 = client.post(
            "/api/credits",
            json={"credit_type": "j_credit", "name": "J-クレジット 2025", "quantity_tco2": 100.0},
        ).json()
        c2 = client.post(
            "/api/credits",
            json={"credit_type": "certificate", "name": "再エネ証書", "quantity_tco2": 50.0},
        ).json()

        allocated = client.post(
            f"/api/credits/{c1['credit_id']}/allocate",
            json={"project_id": project["project_id"], "quantity_tco2": 30.0},
        )
        assert allocated.status_code == 200
        assert allocated.json()["status"] == "available"
        assert allocated.json()["allocated_tco2"] == pytest.approx(30.0)
        assert allocated.json()["allocated_project_id"] == project["project_id"]

        retired = client.post(f"/api/credits/{c2['credit_id']}/retire")
        assert retired.status_code == 200
        assert retired.json()["status"] == "retired"

        summary = client.get("/api/credits/summary").json()
        assert summary["allocated_tco2"] == pytest.approx(30.0)
        assert summary["retired_tco2"] == pytest.approx(50.0)
        assert summary["available_tco2"] == pytest.approx(70.0)


class TestAnnualReport:
    def test_annual_report_pdf(self, client: TestClient):
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=500.0, unit="L", target_month="2026-05", approved=True)
        client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        resp = client.get("/api/reports/annual/2026")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"
