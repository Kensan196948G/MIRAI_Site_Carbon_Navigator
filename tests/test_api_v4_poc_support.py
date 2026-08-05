"""Tests for Phase 6 PoC-support features."""
import io

import pytest
from openpyxl import Workbook
from starlette.testclient import TestClient

from tests.conftest import make_activity, make_emission_factor, make_project


class TestUnitAutoConversion:
    def test_activity_unit_auto_converted(self, client: TestClient):
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        client.post(
            "/api/activities",
            json={
                "project_id": project["project_id"],
                "target_month": "2026-05",
                "category": "fuel",
                "item_name": "軽油",
                "quantity": 0.5,
                "unit": "kL",
            },
        )
        activity = client.get(
            f"/api/activities?project_id={project['project_id']}&target_month=2026-05"
        ).json()[0]
        assert activity["unit"] == "L"
        assert activity["quantity"] == pytest.approx(500.0)
        assert "自動換算" in (activity["note"] or "")


class TestProjectImport:
    def _make_xlsx(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["name", "branch", "work_type", "start_date", "end_date", "description", "close_day"])
        ws.append(["取込工事A", "東京支店", "道路工事", "2026-04-01", "2026-09-30", "取込テスト", 25])
        ws.append(["取込工事B", "大阪支店", "港湾工事", "2026-01-01", "2026-12-31", "取込テスト", 20])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.getvalue()

    def test_import_projects(self, client: TestClient):
        resp = client.post(
            "/api/projects/import",
            files={"file": ("projects.xlsx", self._make_xlsx(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        assert resp.json()["imported"] == 2
        projects = client.get("/api/projects").json()
        assert any(p["name"] == "取込工事A" for p in projects)

    def test_template_download(self, client: TestClient):
        resp = client.get("/api/projects/template")
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"


class TestComparison:
    def test_mom_yoy(self, client: TestClient):
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=100.0, unit="L", target_month="2026-05", approved=True)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=200.0, unit="L", target_month="2026-04", approved=True)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=50.0, unit="L", target_month="2025-05", approved=True)
        for month in ["2026-05", "2026-04", "2025-05"]:
            client.post(
                "/api/emissions/calculate",
                json={"project_id": project["project_id"], "target_month": month},
            )
        resp = client.get(
            f"/api/emissions/comparison?project_id={project['project_id']}&target_month=2026-05"
        )
        data = resp.json()
        assert data["current_total_kg"] == pytest.approx(258.0)
        assert data["previous_month_kg"] == pytest.approx(516.0)
        assert data["mom_ratio"] == pytest.approx(0.5)
        assert data["previous_year_kg"] == pytest.approx(129.0)
        assert data["yoy_ratio"] == pytest.approx(2.0)


class TestMissingMonths:
    def test_missing_months_listed(self, client: TestClient):
        project = make_project(client)
        resp = client.get(f"/api/emissions/missing-months?project_id={project['project_id']}")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
        assert resp.json()[0]["reason"] == "no_data"


class TestMonthStatus:
    def test_month_status(self, client: TestClient):
        project = make_project(client)
        resp = client.get("/api/emissions/month-status?target_month=2026-08")
        assert resp.status_code == 200
        item = [s for s in resp.json() if s["project_id"] == project["project_id"]][0]
        assert item["activity_count"] == 0
        assert item["is_closed"] is False
        assert item["close_day"] == 25
        assert "days_remaining" in item


class TestActivityHistory:
    def test_history_records_co2_impact(self, client: TestClient):
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        activity = make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                                 quantity=100.0, unit="L", target_month="2026-05")
        client.put(
            f"/api/activities/{activity['activity_id']}",
            json={"quantity": 200.0},
        )
        history = client.get(f"/api/activities/{activity['activity_id']}/history").json()
        assert len(history) >= 1
        entry = history[0]
        assert entry["field"] == "quantity"
        assert entry["old_value"] == "100"
        assert entry["new_value"] == "200"
        assert entry["co2_kg_before"] == pytest.approx(258.0)
        assert entry["co2_kg_after"] == pytest.approx(516.0)


class TestForecast:
    def test_forecast(self, client: TestClient):
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        for i, qty in enumerate([100.0, 110.0, 120.0], start=1):
            make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                          quantity=qty, unit="L", target_month=f"2026-0{i}", approved=True)
            client.post(
                "/api/emissions/calculate",
                json={"project_id": project["project_id"], "target_month": f"2026-0{i}"},
            )
        resp = client.get(f"/api/emissions/forecast?project_id={project['project_id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_month"] == "2026-04"
        assert data["forecast_total_kg"] > 0


class TestScenarioSimulation:
    def test_scenario_reduction(self, client: TestClient):
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
        resp = client.post(
            "/api/emissions/scenario-simulate",
            json={
                "project_id": project["project_id"],
                "target_month": "2026-05",
                "adjustments": {"fuel": -10.0, "power": -20.0},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # fuel 1290 -> 1161, power 434 -> 347.2
        assert data["scenario_total_kg"] == pytest.approx(1508.2)
        assert data["reduction_kg"] == pytest.approx(215.8)
        assert "scope1" in data["scope_after"]


class TestZScoreAnomaly:
    def test_zscore_detection(self, client: TestClient):
        project = make_project(client)
        for month, qty in [
            ("2025-12", 100.0), ("2026-01", 110.0), ("2026-02", 95.0),
            ("2026-03", 105.0), ("2026-04", 108.0), ("2026-05", 500.0),
        ]:
            make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                          quantity=qty, unit="L", target_month=month, approved=True)
        resp = client.get(
            f"/api/emissions/anomalies?project_id={project['project_id']}&target_month=2026-05"
        )
        anomalies = resp.json()
        assert len(anomalies) == 1
        assert any("Zスコア" in reason for reason in anomalies[0]["reasons"])
