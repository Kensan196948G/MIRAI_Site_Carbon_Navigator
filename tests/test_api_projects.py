"""
Integration tests for the Projects API (/api/projects).
"""
from starlette.testclient import TestClient

from tests.conftest import make_project


class TestCreateProject:
    def test_create_project_success(self, client: TestClient):
        """有効なデータでプロジェクトを作成すると 201 が返り、正しいフィールドを持つ"""
        payload = {
            "name": "MIRAI 港湾護岸工事",
            "branch": "九州支店",
            "work_type": "土木工事",
            "start_date": "2026-04-01",
            "end_date": "2026-12-31",
            "description": "九州沿岸の護岸補修工事",
            "created_by": "suzuki_taro",
        }
        resp = client.post("/api/projects", json=payload)

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "MIRAI 港湾護岸工事"
        assert data["branch"] == "九州支店"
        assert data["work_type"] == "土木工事"
        assert "project_id" in data
        assert "created_at" in data

    def test_create_project_without_description(self, client: TestClient):
        """description は省略可能（nullable）"""
        payload = {
            "name": "橋梁架設工事",
            "branch": "関東支店",
            "work_type": "橋梁工事",
            "start_date": "2026-05-01",
            "end_date": "2026-10-31",
            "created_by": "tanaka_ichiro",
        }
        resp = client.post("/api/projects", json=payload)

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "橋梁架設工事"

    def test_create_project_returns_uuid(self, client: TestClient):
        """project_id は UUID 形式で自動生成される"""
        project = make_project(client)
        pid = project["project_id"]
        # UUID v4 は 36 文字（ハイフン含む）
        assert len(pid) == 36
        assert pid.count("-") == 4

    def test_create_project_duplicate_name_allowed(self, client: TestClient):
        """同名のプロジェクトは複数作成できる（project_id は異なる UUID が付与される）"""
        payload = {
            "name": "重複テスト工事",
            "branch": "本社",
            "work_type": "その他",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "created_by": "system",
        }
        resp1 = client.post("/api/projects", json=payload)
        resp2 = client.post("/api/projects", json=payload)

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["project_id"] != resp2.json()["project_id"]


class TestListProjects:
    def test_list_projects_empty(self, client: TestClient):
        """プロジェクトが存在しない場合は空リストを返す"""
        resp = client.get("/api/projects")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_projects_returns_all(self, client: TestClient):
        """作成したプロジェクトが全件返る"""
        make_project(client, "p1")
        make_project(client, "p2")
        make_project(client, "p3")

        resp = client.get("/api/projects")

        assert resp.status_code == 200
        assert len(resp.json()) == 3


class TestGetProject:
    def test_get_project_success(self, client: TestClient):
        """存在するプロジェクトを project_id で取得できる"""
        created = make_project(client)
        pid = created["project_id"]

        resp = client.get(f"/api/projects/{pid}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["name"] == created["name"]

    def test_get_project_not_found(self, client: TestClient):
        """存在しない project_id は 404 を返す"""
        resp = client.get("/api/projects/nonexistent-id-xyz")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
