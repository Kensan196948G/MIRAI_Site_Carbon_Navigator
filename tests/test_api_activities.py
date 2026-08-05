"""
Integration tests for the Activities API (/api/activities).
"""
import pytest
from starlette.testclient import TestClient

from tests.conftest import make_activity, make_project


class TestCreateActivity:
    def test_create_activity_success(self, client: TestClient):
        """有効なデータで活動量データを作成すると 201 が返る"""
        project = make_project(client)
        pid = project["project_id"]

        payload = {
            "project_id": pid,
            "target_month": "2026-05",
            "category": "fuel",
            "item_name": "軽油",
            "quantity": 500.0,
            "unit": "L",
            "created_by": "test_user",
        }
        resp = client.post("/api/activities", json=payload)

        assert resp.status_code == 201
        data = resp.json()
        assert data["project_id"] == pid
        assert data["category"] == "fuel"
        assert data["item_name"] == "軽油"
        assert data["quantity"] == pytest.approx(500.0)
        assert data["approved"] is False
        assert "activity_id" in data

    def test_create_activity_project_not_found(self, client: TestClient):
        """存在しない project_id は 404 を返す"""
        payload = {
            "project_id": "nonexistent-project",
            "target_month": "2026-05",
            "category": "fuel",
            "item_name": "軽油",
            "quantity": 100.0,
            "unit": "L",
            "created_by": "test_user",
        }
        resp = client.post("/api/activities", json=payload)

        assert resp.status_code == 404

    def test_create_activity_duplicate(self, client: TestClient):
        """同一プロジェクト・月・カテゴリ・品目の重複登録は 400 を返す"""
        project = make_project(client)
        pid = project["project_id"]

        payload = {
            "project_id": pid,
            "target_month": "2026-05",
            "category": "fuel",
            "item_name": "軽油",
            "quantity": 500.0,
            "unit": "L",
            "created_by": "test_user",
        }
        resp1 = client.post("/api/activities", json=payload)
        resp2 = client.post("/api/activities", json=payload)

        assert resp1.status_code == 201
        assert resp2.status_code == 400

    def test_create_activity_different_month_allowed(self, client: TestClient):
        """月が異なれば同一プロジェクト・カテゴリ・品目でも登録できる"""
        project = make_project(client)
        pid = project["project_id"]

        base_payload = {
            "project_id": pid,
            "category": "fuel",
            "item_name": "軽油",
            "quantity": 200.0,
            "unit": "L",
            "created_by": "test_user",
        }
        resp1 = client.post("/api/activities", json={**base_payload, "target_month": "2026-05"})
        resp2 = client.post("/api/activities", json={**base_payload, "target_month": "2026-06"})

        assert resp1.status_code == 201
        assert resp2.status_code == 201

    def test_create_activity_default_not_approved(self, client: TestClient):
        """新規作成時は approved=False でなければならない"""
        project = make_project(client)
        activity = make_activity(client, project["project_id"])

        assert activity["approved"] is False


class TestListActivities:
    def test_list_activities_all(self, client: TestClient):
        """フィルターなしで全件返る"""
        proj1 = make_project(client, "a")
        proj2 = make_project(client, "b")
        make_activity(client, proj1["project_id"], target_month="2026-05")
        make_activity(client, proj2["project_id"], target_month="2026-05")

        resp = client.get("/api/activities")

        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_activities_filter_by_project(self, client: TestClient):
        """project_id フィルターで指定プロジェクトのみ返る"""
        proj1 = make_project(client, "filter-a")
        proj2 = make_project(client, "filter-b")
        make_activity(client, proj1["project_id"], item_name="軽油", target_month="2026-05")
        make_activity(client, proj1["project_id"], item_name="A重油", target_month="2026-05", category="fuel")
        make_activity(client, proj2["project_id"], item_name="軽油", target_month="2026-05")

        resp = client.get(f"/api/activities?project_id={proj1['project_id']}")

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2
        assert all(r["project_id"] == proj1["project_id"] for r in results)

    def test_list_activities_empty(self, client: TestClient):
        """データなしは空リスト"""
        resp = client.get("/api/activities")

        assert resp.status_code == 200
        assert resp.json() == []


class TestApproveActivity:
    def test_approve_activity_true(self, client: TestClient):
        """approved=True に更新できる"""
        project = make_project(client)
        activity = make_activity(client, project["project_id"])
        aid = activity["activity_id"]

        resp = client.put(f"/api/activities/{aid}/approve", json={"approved": True})

        assert resp.status_code == 200
        assert resp.json()["approved"] is True

    def test_unapprove_activity(self, client: TestClient):
        """一度 approve したものを approved=False に戻せる"""
        project = make_project(client)
        activity = make_activity(client, project["project_id"], approved=True)
        aid = activity["activity_id"]

        resp = client.put(f"/api/activities/{aid}/approve", json={"approved": False})

        assert resp.status_code == 200
        assert resp.json()["approved"] is False

    def test_approve_activity_not_found(self, client: TestClient):
        """存在しない activity_id は 404"""
        resp = client.put("/api/activities/nonexistent-id/approve", json={"approved": True})

        assert resp.status_code == 404


class TestBulkCreateActivities:
    def test_bulk_create_success(self, client: TestClient):
        """複数活動量データを一括作成する"""
        project = make_project(client)
        pid = project["project_id"]

        activities = [
            {
                "project_id": pid,
                "target_month": "2026-05",
                "category": "fuel",
                "item_name": "軽油",
                "quantity": 300.0,
                "unit": "L",
                "created_by": "test_user",
            },
            {
                "project_id": pid,
                "target_month": "2026-05",
                "category": "power",
                "item_name": "電力",
                "quantity": 1000.0,
                "unit": "kWh",
                "created_by": "test_user",
            },
            {
                "project_id": pid,
                "target_month": "2026-05",
                "category": "material",
                "item_name": "生コンクリート",
                "quantity": 50.0,
                "unit": "t",
                "created_by": "test_user",
            },
        ]
        resp = client.post("/api/activities/bulk", json=activities)

        assert resp.status_code == 201
        results = resp.json()
        assert len(results) == 3

    def test_bulk_create_partial_success(self, client: TestClient):
        """一部が失敗しても成功分は登録される（部分成功）"""
        project = make_project(client)
        pid = project["project_id"]

        # 先に 1 件登録しておく（重複になる）
        make_activity(client, pid, item_name="軽油", target_month="2026-05")

        activities = [
            {
                "project_id": pid,
                "target_month": "2026-05",
                "category": "fuel",
                "item_name": "軽油",  # 重複 → スキップ
                "quantity": 999.0,
                "unit": "L",
                "created_by": "test_user",
            },
            {
                "project_id": pid,
                "target_month": "2026-05",
                "category": "power",
                "item_name": "電力",  # 新規 → 成功
                "quantity": 800.0,
                "unit": "kWh",
                "created_by": "test_user",
            },
        ]
        resp = client.post("/api/activities/bulk", json=activities)

        # 成功分がある場合は 201
        assert resp.status_code == 201
        assert len(resp.json()) == 1

    def test_bulk_create_all_fail(self, client: TestClient):
        """全件失敗の場合は 400"""
        activities = [
            {
                "project_id": "no-such-project",
                "target_month": "2026-05",
                "category": "fuel",
                "item_name": "軽油",
                "quantity": 100.0,
                "unit": "L",
                "created_by": "test_user",
            }
        ]
        resp = client.post("/api/activities/bulk", json=activities)

        assert resp.status_code == 400
