"""
Integration tests for the Emission Factors API (/api/factors).
"""
import pytest
from starlette.testclient import TestClient

from tests.conftest import make_emission_factor


class TestCreateFactor:
    def test_create_factor_success(self, client: TestClient):
        """有効なデータで排出係数を作成すると 201 が返る"""
        payload = {
            "category": "fuel",
            "item_name": "軽油",
            "unit": "L",
            "factor_value": 2.58,
            "effective_from": "2025-04-01",
            "source": "環境省温室効果ガス排出係数一覧",
        }
        resp = client.post("/api/factors", json=payload)

        assert resp.status_code == 201
        data = resp.json()
        assert data["category"] == "fuel"
        assert data["item_name"] == "軽油"
        assert data["unit"] == "L"
        assert data["factor_value"] == pytest.approx(2.58)
        assert "factor_id" in data
        assert "created_at" in data

    def test_create_factor_power(self, client: TestClient):
        """電力カテゴリの排出係数を作成できる"""
        resp = client.post("/api/factors", json={
            "category": "power",
            "item_name": "電力",
            "unit": "kWh",
            "factor_value": 0.434,
            "effective_from": "2025-01-01",
            "source": "電気事業者別排出係数",
        })

        assert resp.status_code == 201
        assert resp.json()["factor_value"] == pytest.approx(0.434)

    def test_create_factor_material(self, client: TestClient):
        """材料カテゴリの排出係数を作成できる"""
        resp = client.post("/api/factors", json={
            "category": "material",
            "item_name": "生コンクリート",
            "unit": "t",
            "factor_value": 350.0,
            "effective_from": "2025-01-01",
            "source": "建設工事施工統計調査",
        })

        assert resp.status_code == 201
        assert resp.json()["category"] == "material"

    def test_create_factor_returns_uuid(self, client: TestClient):
        """factor_id は UUID 形式で自動生成される"""
        factor = make_emission_factor(client)
        fid = factor["factor_id"]
        assert len(fid) == 36
        assert fid.count("-") == 4

    def test_create_multiple_factors_same_category(self, client: TestClient):
        """同一カテゴリ・品目で複数バージョン（異なる effective_from）を登録できる"""
        payload_base = {
            "category": "fuel",
            "item_name": "軽油",
            "unit": "L",
            "source": "環境省",
        }
        resp1 = client.post("/api/factors", json={**payload_base, "factor_value": 2.50, "effective_from": "2020-01-01"})
        resp2 = client.post("/api/factors", json={**payload_base, "factor_value": 2.58, "effective_from": "2025-04-01"})

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["factor_id"] != resp2.json()["factor_id"]


class TestListFactors:
    def test_list_factors_empty(self, client: TestClient):
        """データなしは空リスト"""
        resp = client.get("/api/factors")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_factors_all(self, client: TestClient):
        """全排出係数が返る"""
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_emission_factor(client, category="power", item_name="電力", unit="kWh", factor_value=0.434)
        make_emission_factor(client, category="material", item_name="生コンクリート", unit="t", factor_value=350.0)

        resp = client.get("/api/factors")

        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_list_factors_by_category(self, client: TestClient):
        """category フィルターで指定カテゴリのみ返る"""
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_emission_factor(client, category="fuel", item_name="A重油", unit="L", factor_value=2.71)
        make_emission_factor(client, category="power", item_name="電力", unit="kWh", factor_value=0.434)

        resp = client.get("/api/factors?category=fuel")

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2
        assert all(r["category"] == "fuel" for r in results)

    def test_list_factors_by_category_power(self, client: TestClient):
        """power カテゴリのみフィルタリングできる"""
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_emission_factor(client, category="power", item_name="電力", unit="kWh", factor_value=0.434)

        resp = client.get("/api/factors?category=power")

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["category"] == "power"

    def test_list_factors_unknown_category_returns_empty(self, client: TestClient):
        """存在しないカテゴリはフィルターで空リストを返す"""
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)

        resp = client.get("/api/factors?category=unknown_category")

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetFactor:
    def test_get_factor_success(self, client: TestClient):
        """存在する factor_id で取得できる"""
        created = make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        fid = created["factor_id"]

        resp = client.get(f"/api/factors/{fid}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["factor_id"] == fid
        assert data["item_name"] == "軽油"
        assert data["factor_value"] == pytest.approx(2.58)

    def test_get_factor_not_found(self, client: TestClient):
        """存在しない factor_id は 404 を返す"""
        resp = client.get("/api/factors/nonexistent-factor-id")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_factor_correct_values(self, client: TestClient):
        """取得した排出係数の全フィールドが正しい"""
        payload = {
            "category": "transport",
            "item_name": "ダンプトラック",
            "unit": "km",
            "factor_value": 0.098,
            "effective_from": "2024-06-01",
            "source": "国土交通省資料",
        }
        resp_create = client.post("/api/factors", json=payload)
        fid = resp_create.json()["factor_id"]

        resp_get = client.get(f"/api/factors/{fid}")

        assert resp_get.status_code == 200
        data = resp_get.json()
        assert data["category"] == "transport"
        assert data["item_name"] == "ダンプトラック"
        assert data["unit"] == "km"
        assert data["factor_value"] == pytest.approx(0.098)
        assert data["effective_from"] == "2024-06-01"
        assert data["source"] == "国土交通省資料"
