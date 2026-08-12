"""Tests for v2 features: PDF, benchmark, anomalies, notifications, users."""
import pytest
from starlette.testclient import TestClient

from tests.conftest import make_activity, make_emission_factor, make_project


def _create_calculated_project(client: TestClient, name: str, work_type: str, month: str = "2026-05") -> dict:
    project = make_project(client)
    # make_project always uses 土木工事; update to requested type
    client.put(
        f"/api/projects/{project['project_id']}",
        json={"name": name, "work_type": work_type},
    )
    make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
    make_activity(
        client, project["project_id"], category="fuel", item_name="軽油",
        quantity=500.0, unit="L", target_month=month, approved=True,
    )
    client.post(
        "/api/emissions/calculate",
        json={"project_id": project["project_id"], "target_month": month},
    )
    return client.get(f"/api/projects/{project['project_id']}").json()


class TestPDFReport:
    def test_pdf_report_download(self, client: TestClient):
        project = _create_calculated_project(client, "PDF対象", "土木工事")
        resp = client.get(
            f"/api/reports/monthly/{project['project_id']}/2026-05?format=pdf"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"


class TestBenchmark:
    def test_benchmark_compares_same_work_type(self, client: TestClient):
        _create_calculated_project(client, "対象工事", "道路工事")
        peer = _create_calculated_project(client, "比較工事", "道路工事")

        resp = client.get(
            f"/api/emissions/benchmark?project_id={peer['project_id']}&target_month=2026-05"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["peer_project_count"] == 1
        assert data["current_total_kg"] == pytest.approx(1290.0)
        assert data["peer_avg_monthly_kg"] == pytest.approx(1290.0)
        assert data["comparison_ratio"] == pytest.approx(1.0)

    def test_benchmark_no_peers(self, client: TestClient):
        project = _create_calculated_project(client, "単独工事", "特殊工事")
        resp = client.get(
            f"/api/emissions/benchmark?project_id={project['project_id']}&target_month=2026-05"
        )
        data = resp.json()
        assert data["peer_project_count"] == 0
        assert data["peer_avg_monthly_kg"] is None


class TestAnomalies:
    def test_anomaly_previous_month_ratio(self, client: TestClient):
        project = make_project(client)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=100.0, unit="L", target_month="2026-04", approved=True)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=500.0, unit="L", target_month="2026-05", approved=True)

        resp = client.get(
            f"/api/emissions/anomalies?project_id={project['project_id']}&target_month=2026-05"
        )
        assert resp.status_code == 200
        anomalies = resp.json()
        assert len(anomalies) == 1
        assert anomalies[0]["item_name"] == "軽油"
        assert any("前月比" in reason for reason in anomalies[0]["reasons"])

    def test_no_anomaly_when_stable(self, client: TestClient):
        project = make_project(client)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=100.0, unit="L", target_month="2026-04", approved=True)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=110.0, unit="L", target_month="2026-05", approved=True)
        resp = client.get(
            f"/api/emissions/anomalies?project_id={project['project_id']}&target_month=2026-05"
        )
        assert resp.json() == []


class TestNotifications:
    def test_activity_create_notifies_reviewer(self, client_pair):
        admin, reviewer, _ = client_pair
        project = make_project(admin)
        make_activity(admin, project["project_id"], category="fuel", item_name="軽油",
                      quantity=100.0, unit="L", target_month="2026-05")

        resp = reviewer.get("/api/notifications?unread_only=true")
        assert resp.status_code == 200
        notifications = resp.json()
        assert any("活動量が登録されました" in n["message"] for n in notifications)

        unread = reviewer.get("/api/notifications/unread-count").json()
        assert unread["count"] >= 1

    def test_mark_read(self, client_pair):
        admin, reviewer, _ = client_pair
        project = make_project(admin)
        make_activity(admin, project["project_id"], category="fuel", item_name="軽油",
                      quantity=100.0, unit="L", target_month="2026-05")
        notif = reviewer.get("/api/notifications?unread_only=true").json()[0]
        resp = reviewer.put(f"/api/notifications/{notif['notification_id']}/read")
        assert resp.status_code == 204
        remaining = [n for n in reviewer.get("/api/notifications?unread_only=true").json()]
        assert not any(n["notification_id"] == notif["notification_id"] for n in remaining)

    def test_approval_notifies_site(self, client_pair):
        admin, _, site = client_pair
        project = make_project(admin)
        activity = make_activity(admin, project["project_id"], category="fuel", item_name="軽油",
                                 quantity=100.0, unit="L", target_month="2026-05")
        admin.put(f"/api/activities/{activity['activity_id']}/approve", json={"approved": True})
        notifications = site.get("/api/notifications?unread_only=true").json()
        assert any("承認されました" in n["message"] for n in notifications)

    def test_missing_factor_notifies_admin(self, client: TestClient):
        project = make_project(client)
        make_activity(client, project["project_id"], category="fuel", item_name="A重油",
                      quantity=100.0, unit="L", target_month="2026-05", approved=True)
        client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        notifications = client.get("/api/notifications?unread_only=true").json()
        assert any("排出係数未設定" in n["message"] for n in notifications)


class TestUserManagement:
    def test_update_user_role_and_password(self, client: TestClient):
        created = client.post(
            "/api/users",
            json={"username": "tmpuser", "password": "oldpass123", "role": "site"},
        ).json()
        resp = client.put(
            f"/api/users/{created['user_id']}",
            json={"role": "reviewer", "password": "newpass4567"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "reviewer"

        login = client.post(
            "/api/auth/login",
            json={"username": "tmpuser", "password": "newpass4567"},
        )
        assert login.status_code == 200
        assert login.json()["user"]["role"] == "reviewer"

    def test_deactivate_user_blocks_login(self, client: TestClient):
        created = client.post(
            "/api/users",
            json={"username": "temp2", "password": "pass123456", "role": "viewer"},
        ).json()
        client.put(f"/api/users/{created['user_id']}/active?is_active=false")
        login = client.post(
            "/api/auth/login",
            json={"username": "temp2", "password": "pass123456"},
        )
        assert login.status_code == 401
