"""
Integration tests for the Emissions API (/api/emissions).
"""
import pytest
from starlette.testclient import TestClient

from tests.conftest import make_activity, make_emission_factor, make_project

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_fuel_scenario(client: TestClient, quantity: float = 500.0, target_month: str = "2026-05"):
    """
    よく使うシナリオ: プロジェクト + 排出係数 + 承認済み活動量を作成し、
    それぞれのオブジェクトを返す。
    """
    project = make_project(client)
    factor = make_emission_factor(
        client,
        category="fuel",
        item_name="軽油",
        unit="L",
        factor_value=2.58,
    )
    activity = make_activity(
        client,
        project_id=project["project_id"],
        category="fuel",
        item_name="軽油",
        quantity=quantity,
        unit="L",
        target_month=target_month,
        approved=True,
    )
    return project, factor, activity


# ---------------------------------------------------------------------------
# POST /api/emissions/calculate
# ---------------------------------------------------------------------------

class TestCalculateEmissions:
    def test_calculate_emissions_basic(self, client: TestClient):
        """承認済み活動量が正しい CO2 値で計算される"""
        project, factor, activity = _setup_fuel_scenario(client, quantity=500.0)

        resp = client.post("/api/emissions/calculate", json={
            "project_id": project["project_id"],
            "target_month": "2026-05",
        })

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["co2_kg"] == pytest.approx(1290.0)  # 500 × 2.58

    def test_calculate_returns_result_fields(self, client: TestClient):
        """レスポンスに必須フィールドが含まれる"""
        project, _, _ = _setup_fuel_scenario(client)

        resp = client.post("/api/emissions/calculate", json={
            "project_id": project["project_id"],
            "target_month": "2026-05",
        })

        assert resp.status_code == 200
        r = resp.json()[0]
        assert "result_id" in r
        assert "activity_id" in r
        assert "factor_id" in r
        assert "co2_kg" in r
        assert "calculated_at" in r

    def test_calculate_project_not_found(self, client: TestClient):
        """存在しない project_id は 404"""
        resp = client.post("/api/emissions/calculate", json={
            "project_id": "no-such-project",
            "target_month": "2026-05",
        })

        assert resp.status_code == 404

    def test_calculate_unapproved_excluded(self, client: TestClient):
        """未承認の活動量は計算結果に含まれない"""
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)

        # 未承認で作成
        make_activity(
            client,
            project_id=project["project_id"],
            category="fuel",
            item_name="軽油",
            quantity=500.0,
            unit="L",
            target_month="2026-05",
            approved=False,  # ← 未承認
        )

        resp = client.post("/api/emissions/calculate", json={
            "project_id": project["project_id"],
            "target_month": "2026-05",
        })

        assert resp.status_code == 200
        assert resp.json() == []  # 未承認なので結果なし

    def test_calculate_no_matching_factor(self, client: TestClient):
        """排出係数がない活動量はスキップされる"""
        project = make_project(client)
        # 係数を登録しない

        make_activity(
            client,
            project_id=project["project_id"],
            category="fuel",
            item_name="A重油",
            quantity=200.0,
            unit="L",
            target_month="2026-05",
            approved=True,
        )

        resp = client.post("/api/emissions/calculate", json={
            "project_id": project["project_id"],
            "target_month": "2026-05",
        })

        assert resp.status_code == 200
        assert resp.json() == []

    def test_calculate_multiple_activities(self, client: TestClient):
        """複数承認済み活動量が全て計算される"""
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_emission_factor(client, category="power", item_name="電力", unit="kWh", factor_value=0.434)

        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=500.0, unit="L", target_month="2026-05", approved=True)
        make_activity(client, project["project_id"], category="power", item_name="電力",
                      quantity=1200.0, unit="kWh", target_month="2026-05", approved=True)

        resp = client.post("/api/emissions/calculate", json={
            "project_id": project["project_id"],
            "target_month": "2026-05",
        })

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2

        co2_values = [r["co2_kg"] for r in results]
        # pytest.approx() does not implement __hash__, so use any() for membership check
        assert any(v == pytest.approx(1290.0) for v in co2_values)   # fuel: 500 × 2.58
        assert any(v == pytest.approx(520.8) for v in co2_values)    # power: 1200 × 0.434


# ---------------------------------------------------------------------------
# GET /api/emissions/summary
# ---------------------------------------------------------------------------

class TestEmissionsSummary:
    def test_summary_empty(self, client: TestClient):
        """計算結果がない場合は空リスト"""
        resp = client.get("/api/emissions/summary")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_summary_after_calculation(self, client: TestClient):
        """計算後にサマリーがカテゴリ別合計を返す"""
        project, _, _ = _setup_fuel_scenario(client, quantity=500.0)

        client.post("/api/emissions/calculate", json={
            "project_id": project["project_id"],
            "target_month": "2026-05",
        })

        resp = client.get(f"/api/emissions/summary?project_id={project['project_id']}")

        assert resp.status_code == 200
        summary = resp.json()
        assert len(summary) == 1
        assert summary[0]["category"] == "fuel"
        assert summary[0]["total_co2_kg"] == pytest.approx(1290.0)

    def test_summary_aggregates_multiple_categories(self, client: TestClient):
        """複数カテゴリがそれぞれ集計される"""
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_emission_factor(client, category="power", item_name="電力", unit="kWh", factor_value=0.434)

        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=500.0, unit="L", target_month="2026-05", approved=True)
        make_activity(client, project["project_id"], category="power", item_name="電力",
                      quantity=1200.0, unit="kWh", target_month="2026-05", approved=True)

        client.post("/api/emissions/calculate", json={
            "project_id": project["project_id"],
            "target_month": "2026-05",
        })

        resp = client.get(f"/api/emissions/summary?project_id={project['project_id']}")

        assert resp.status_code == 200
        summary = {item["category"]: item["total_co2_kg"] for item in resp.json()}
        assert summary["fuel"] == pytest.approx(1290.0)
        assert summary["power"] == pytest.approx(520.8)


# ---------------------------------------------------------------------------
# GET /api/emissions/reduction/{project_id}/{target_month}
# ---------------------------------------------------------------------------

class TestReductionSuggestions:
    def test_reduction_suggestions_project_not_found(self, client: TestClient):
        """存在しない project_id は 404"""
        resp = client.get("/api/emissions/reduction/no-such-project/2026-05")

        assert resp.status_code == 404

    def test_reduction_suggestions_empty_results(self, client: TestClient):
        """計算結果がない場合は空リスト"""
        project = make_project(client)

        resp = client.get(f"/api/emissions/reduction/{project['project_id']}/2026-05")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_reduction_suggestions_after_calculation(self, client: TestClient):
        """計算後に削減提案が返される"""
        project, _, _ = _setup_fuel_scenario(client, quantity=500.0)

        client.post("/api/emissions/calculate", json={
            "project_id": project["project_id"],
            "target_month": "2026-05",
        })

        resp = client.get(f"/api/emissions/reduction/{project['project_id']}/2026-05")

        assert resp.status_code == 200
        suggestions = resp.json()
        assert len(suggestions) >= 1

        s = suggestions[0]
        assert "category" in s
        assert "total_co2_kg" in s
        assert "rank" in s
        assert "suggestions" in s
        assert isinstance(s["suggestions"], list)
        assert len(s["suggestions"]) > 0

    def test_reduction_suggestions_ranked_by_co2(self, client: TestClient):
        """複数カテゴリがある場合、CO2 量の多い順に rank が付く"""
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_emission_factor(client, category="power", item_name="電力", unit="kWh", factor_value=0.434)

        # fuel: 500 × 2.58 = 1290 (大)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=500.0, unit="L", target_month="2026-05", approved=True)
        # power: 100 × 0.434 = 43.4 (小)
        make_activity(client, project["project_id"], category="power", item_name="電力",
                      quantity=100.0, unit="kWh", target_month="2026-05", approved=True)

        client.post("/api/emissions/calculate", json={
            "project_id": project["project_id"],
            "target_month": "2026-05",
        })

        resp = client.get(f"/api/emissions/reduction/{project['project_id']}/2026-05")

        assert resp.status_code == 200
        suggestions = resp.json()
        assert len(suggestions) == 2
        # rank=1 は CO2 が最大のカテゴリ（fuel）
        assert suggestions[0]["rank"] == 1
        assert suggestions[0]["category"] == "fuel"
        assert suggestions[1]["rank"] == 2
