"""Tests for new capabilities: CRUD, trend, coverage, import, actions, audit."""
import io

import pytest
from openpyxl import Workbook
from starlette.testclient import TestClient

from tests.conftest import make_activity, make_emission_factor, make_project


def _setup_emission_scenario(client: TestClient, month: str = "2026-05"):
    project = make_project(client)
    make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
    make_activity(
        client,
        project["project_id"],
        category="fuel",
        item_name="軽油",
        quantity=500.0,
        unit="L",
        target_month=month,
        approved=True,
    )
    return project


class TestProjectCRUD:
    def test_update_project(self, client: TestClient):
        project = make_project(client)
        resp = client.put(
            f"/api/projects/{project['project_id']}",
            json={"name": "更新後工事名", "work_type": "橋梁工事"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "更新後工事名"
        assert resp.json()["work_type"] == "橋梁工事"

    def test_delete_project(self, client: TestClient):
        project = make_project(client)
        resp = client.delete(f"/api/projects/{project['project_id']}")
        assert resp.status_code == 204
        assert client.get(f"/api/projects/{project['project_id']}").status_code == 404

    def test_update_missing_project_404(self, client: TestClient):
        resp = client.put("/api/projects/not-found", json={"name": "x"})
        assert resp.status_code == 404


class TestFactorCRUD:
    def test_update_factor(self, client: TestClient):
        factor = make_emission_factor(client, factor_value=2.58)
        resp = client.put(
            f"/api/factors/{factor['factor_id']}",
            json={"factor_value": 2.60, "source": "更新済み出典"},
        )
        assert resp.status_code == 200
        assert resp.json()["factor_value"] == pytest.approx(2.60)
        assert resp.json()["source"] == "更新済み出典"

    def test_delete_factor(self, client: TestClient):
        factor = make_emission_factor(client)
        resp = client.delete(f"/api/factors/{factor['factor_id']}")
        assert resp.status_code == 204
        assert client.get(f"/api/factors/{factor['factor_id']}").status_code == 404


class TestActivityCRUD:
    def test_update_activity_resets_approval(self, client: TestClient):
        project = make_project(client)
        activity = make_activity(
            client, project["project_id"], approved=True,
        )
        resp = client.put(
            f"/api/activities/{activity['activity_id']}",
            json={"quantity": 600.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["quantity"] == pytest.approx(600.0)
        assert data["approved"] is False
        assert data["approved_by"] is None

    def test_delete_activity(self, client: TestClient):
        project = make_project(client)
        activity = make_activity(client, project["project_id"])
        resp = client.delete(f"/api/activities/{activity['activity_id']}")
        assert resp.status_code == 204

    def test_invalid_month_rejected(self, client: TestClient):
        project = make_project(client)
        resp = client.post(
            "/api/activities",
            json={
                "project_id": project["project_id"],
                "target_month": "2026/05",
                "category": "fuel",
                "item_name": "軽油",
                "quantity": 10.0,
                "unit": "L",
            },
        )
        assert resp.status_code == 422

    def test_negative_quantity_rejected(self, client: TestClient):
        project = make_project(client)
        resp = client.post(
            "/api/activities",
            json={
                "project_id": project["project_id"],
                "target_month": "2026-05",
                "category": "fuel",
                "item_name": "軽油",
                "quantity": -10.0,
                "unit": "L",
            },
        )
        assert resp.status_code == 422


class TestCalculationEnhancements:
    def test_calculation_returns_item_details(self, client: TestClient):
        project = _setup_emission_scenario(client)
        resp = client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        assert resp.status_code == 200
        item = resp.json()[0]
        assert item["category"] == "fuel"
        assert item["item_name"] == "軽油"
        assert item["quantity"] == pytest.approx(500.0)
        assert item["unit"] == "L"
        assert item["factor_value"] == pytest.approx(2.58)
        assert item["co2_kg"] == pytest.approx(1290.0)

    def test_future_factor_not_applied_to_past_month(self, client: TestClient):
        """effective_from が対象月より未来の係数は使われない"""
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L",
                             factor_value=2.58, effective_from="2026-01-01")
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L",
                             factor_value=9.99, effective_from="2026-06-01")
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=100.0, unit="L", target_month="2026-05", approved=True)

        resp = client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        item = resp.json()[0]
        assert item["factor_value"] == pytest.approx(2.58)
        assert item["co2_kg"] == pytest.approx(258.0)

    def test_trend_returns_monthly_totals(self, client: TestClient):
        project = _setup_emission_scenario(client, month="2026-04")
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=100.0, unit="L", target_month="2026-05", approved=True)
        client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-04"},
        )
        client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        resp = client.get(f"/api/emissions/trend?project_id={project['project_id']}")
        assert resp.status_code == 200
        months = {m["target_month"]: m for m in resp.json()}
        assert months["2026-04"]["total_co2_kg"] == pytest.approx(1290.0)
        assert months["2026-05"]["total_co2_kg"] == pytest.approx(258.0)

    def test_missing_factors_endpoint(self, client: TestClient):
        project = make_project(client)
        make_activity(client, project["project_id"], category="fuel", item_name="A重油",
                      quantity=10.0, unit="L", target_month="2026-05", approved=True)
        resp = client.get(
            f"/api/emissions/missing-factors?project_id={project['project_id']}&target_month=2026-05"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["item_name"] == "A重油"


class TestReports:
    def test_csv_report(self, client: TestClient):
        project = _setup_emission_scenario(client)
        client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        resp = client.get(
            f"/api/reports/monthly/{project['project_id']}/2026-05?format=csv"
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        body = resp.content.decode("utf-8-sig")
        assert "軽油" in body
        assert "1290" in body

    def test_excel_template_download(self, client: TestClient):
        resp = client.get("/api/activities/template")
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"  # xlsx zip magic


class TestActivityImport:
    def test_import_xlsx(self, client: TestClient):
        project = make_project(client)
        wb = Workbook()
        ws = wb.active
        ws.append(["project_id", "target_month", "category", "item_name", "quantity", "unit"])
        ws.append([project["project_id"], "2026-06", "fuel", "軽油", 100.0, "L"])
        ws.append([project["project_id"], "2026-06", "power", "電力", 200.0, "kWh"])
        ws.append([project["project_id"], "2026-06", "fuel", "軽油", 300.0, "L"])  # duplicate
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        resp = client.post(
            "/api/activities/import",
            files={"file": ("input.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2
        assert data["skipped"] == 1

    def test_import_rejects_non_excel(self, client: TestClient):
        resp = client.post(
            "/api/activities/import",
            files={"file": ("data.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400


class TestReductionActions:
    def test_crud_cycle(self, client: TestClient):
        project = make_project(client)
        created = client.post(
            "/api/actions",
            json={
                "project_id": project["project_id"],
                "target_month": "2026-05",
                "category": "fuel",
                "suggestion": "待機時間削減による燃料消費低減",
                "estimated_reduction_kg": 100.0,
            },
        )
        assert created.status_code == 201
        action_id = created.json()["action_id"]

        listed = client.get(f"/api/actions?project_id={project['project_id']}")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = client.put(
            f"/api/actions/{action_id}",
            json={"status": "implemented", "actual_reduction_kg": 80.0},
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "implemented"

        deleted = client.delete(f"/api/actions/{action_id}")
        assert deleted.status_code == 204


class TestAudit:
    def test_audit_logs_recorded(self, client: TestClient):
        project = make_project(client)
        resp = client.get("/api/audit-logs")
        assert resp.status_code == 200
        logs = resp.json()
        assert any(
            log["resource_type"] == "project" and log["resource_id"] == project["project_id"]
            for log in logs
        )
        assert any(log["action"] == "login" for log in logs)
