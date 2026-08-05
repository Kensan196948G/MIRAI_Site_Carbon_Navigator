"""Tests for PoC features: demo data, site feedback, SBTi targets, Scope summary."""
import pytest
from starlette.testclient import TestClient

from tests.conftest import make_activity, make_emission_factor, make_project


class TestDemoData:
    def test_generate_demo_data(self, client: TestClient):
        resp = client.post("/api/demo/generate")
        assert resp.status_code == 201
        data = resp.json()
        assert data["project_count"] == 2
        assert data["activity_count"] > 0
        assert data["result_count"] > 0
        assert data["action_count"] >= 4
        assert data["feedback_count"] >= 4

    def test_generate_is_idempotent(self, client: TestClient):
        first = client.post("/api/demo/generate").json()
        second = client.post("/api/demo/generate").json()
        assert second["project_count"] == first["project_count"] == 2
        assert second["activity_count"] == first["activity_count"]

    def test_status_and_clear(self, client: TestClient):
        client.post("/api/demo/generate")
        status = client.get("/api/demo/status").json()
        assert status["project_count"] == 2
        cleared = client.delete("/api/demo/clear").json()
        assert cleared["removed"] == 2
        assert client.get("/api/demo/status").json()["project_count"] == 0

    def test_viewer_cannot_generate(self, viewer_client: TestClient):
        resp = viewer_client.post("/api/demo/generate")
        assert resp.status_code == 403


class TestSiteFeedback:
    def test_feedback_crud(self, client: TestClient):
        project = make_project(client)
        created = client.post(
            "/api/feedbacks",
            json={
                "project_id": project["project_id"],
                "target_month": "2026-05",
                "category": "fuel",
                "content": "アイドリング時間が長い",
            },
        )
        assert created.status_code == 201
        data = created.json()
        assert data["status"] == "open"
        assert data["created_by"] == "admin"

        listed = client.get(f"/api/feedbacks?project_id={project['project_id']}")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = client.put(
            f"/api/feedbacks/{data['feedback_id']}",
            json={"status": "resolved", "content": "アイドリング時間が長い（対応済み）"},
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "resolved"

        deleted = client.delete(f"/api/feedbacks/{data['feedback_id']}")
        assert deleted.status_code == 204

    def test_feedback_invalid_status(self, client: TestClient):
        project = make_project(client)
        fb = client.post(
            "/api/feedbacks",
            json={"project_id": project["project_id"], "target_month": "2026-05", "content": "test"},
        ).json()
        resp = client.put(f"/api/feedbacks/{fb['feedback_id']}", json={"status": "invalid"})
        assert resp.status_code == 400

    def test_feedback_notifies_reviewer(self, client_pair):
        admin, reviewer, _ = client_pair
        project = make_project(admin)
        admin.post(
            "/api/feedbacks",
            json={"project_id": project["project_id"], "target_month": "2026-05", "content": "改善要望"},
        )
        notifications = reviewer.get("/api/notifications?unread_only=true").json()
        assert any("現場フィードバック" in n["message"] for n in notifications)

    def test_delete_project_cascades_feedback(self, client: TestClient):
        project = make_project(client)
        client.post(
            "/api/feedbacks",
            json={"project_id": project["project_id"], "target_month": "2026-05", "content": "test"},
        )
        client.delete(f"/api/projects/{project['project_id']}")
        assert client.get("/api/feedbacks").json() == []


class TestSbtiTargets:
    def test_sbti_crud(self, client: TestClient):
        created = client.post(
            "/api/sbti/targets",
            json={
                "scope": "scope1",
                "name": "Scope1+2 42%削減",
                "base_year": 2024,
                "target_year": 2030,
                "base_emissions_kg": 100000.0,
                "reduction_percent": 42.0,
            },
        )
        assert created.status_code == 201
        data = created.json()
        assert data["scope"] == "scope1"
        assert data["is_active"] is True

        updated = client.put(
            f"/api/sbti/targets/{data['target_id']}",
            json={"reduction_percent": 50.0},
        )
        assert updated.status_code == 200
        assert updated.json()["reduction_percent"] == pytest.approx(50.0)

        assert client.delete(f"/api/sbti/targets/{data['target_id']}").status_code == 204

    def test_progress_calculation(self, client: TestClient):
        client.post(
            "/api/sbti/targets",
            json={
                "scope": "scope1",
                "name": "Scope1 削減",
                "base_year": 2024,
                "target_year": 2030,
                "base_emissions_kg": 1290.0,
                "reduction_percent": 50.0,
            },
        )
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=500.0, unit="L", target_month="2026-05", approved=True)
        client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        resp = client.get("/api/sbti/progress")
        assert resp.status_code == 200
        item = resp.json()[0]
        assert item["scope"] == "scope1"
        assert item["current_emissions_kg"] == pytest.approx(1290.0)
        assert item["target_emissions_kg"] == pytest.approx(645.0)
        assert item["reduction_achieved_percent"] == pytest.approx(0.0)
        assert item["on_track"] is False

    def test_invalid_scope_rejected(self, client: TestClient):
        resp = client.post(
            "/api/sbti/targets",
            json={
                "scope": "scope9",
                "name": "x",
                "base_year": 2024,
                "target_year": 2030,
                "base_emissions_kg": 1000.0,
                "reduction_percent": 10.0,
            },
        )
        assert resp.status_code == 400


class TestScopeSummary:
    def test_scope_summary(self, client: TestClient):
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_emission_factor(client, category="power", item_name="電力", unit="kWh", factor_value=0.434)
        make_emission_factor(client, category="material", item_name="鋼材", unit="t", factor_value=2000.0)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=500.0, unit="L", target_month="2026-05", approved=True)
        make_activity(client, project["project_id"], category="power", item_name="電力",
                      quantity=1000.0, unit="kWh", target_month="2026-05", approved=True)
        make_activity(client, project["project_id"], category="material", item_name="鋼材",
                      quantity=2.0, unit="t", target_month="2026-05", approved=True)
        client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        resp = client.get(
            f"/api/emissions/scope-summary?project_id={project['project_id']}&target_month=2026-05"
        )
        assert resp.status_code == 200
        by_scope = {item["scope"]: item for item in resp.json()}
        assert by_scope["scope1"]["total_co2_kg"] == pytest.approx(1290.0)
        assert by_scope["scope2"]["total_co2_kg"] == pytest.approx(434.0)
        assert by_scope["scope3"]["total_co2_kg"] == pytest.approx(4000.0)

    def test_scope_summary_by_year(self, client: TestClient):
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=100.0, unit="L", target_month="2025-12", approved=True)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=200.0, unit="L", target_month="2026-01", approved=True)
        client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2025-12"},
        )
        client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-01"},
        )
        resp = client.get(
            f"/api/emissions/scope-summary?project_id={project['project_id']}&year=2026"
        )
        by_scope = {item["scope"]: item for item in resp.json()}
        assert by_scope["scope1"]["total_co2_kg"] == pytest.approx(516.0)
