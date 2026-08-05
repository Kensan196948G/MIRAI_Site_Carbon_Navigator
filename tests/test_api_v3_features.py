"""Tests for v3 features: monthly close, copy, reminders, export, comments,
unit conversion, supplier factors, project card, branches, telematics, portal."""
import io
import zipfile

import pytest
from starlette.testclient import TestClient

from tests.conftest import make_activity, make_emission_factor, make_project


class TestMonthlyClose:
    def test_close_blocks_mutations(self, client: TestClient):
        project = make_project(client)
        activity = make_activity(client, project["project_id"], target_month="2026-05")

        close = client.post(
            "/api/closes",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        assert close.status_code == 201

        # activity create blocked
        resp = client.post(
            "/api/activities",
            json={
                "project_id": project["project_id"],
                "target_month": "2026-05",
                "category": "power",
                "item_name": "電力",
                "quantity": 100.0,
                "unit": "kWh",
            },
        )
        assert resp.status_code == 400
        assert "締め済み" in resp.json()["detail"]

        # approve blocked
        resp = client.put(
            f"/api/activities/{activity['activity_id']}/approve",
            json={"approved": True},
        )
        assert resp.status_code == 400

        # update blocked
        resp = client.put(
            f"/api/activities/{activity['activity_id']}",
            json={"quantity": 999.0},
        )
        assert resp.status_code == 400

        # calculate blocked
        resp = client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        assert resp.status_code == 400

    def test_unlock_allows_again(self, client: TestClient):
        project = make_project(client)
        close = client.post(
            "/api/closes",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        ).json()
        assert client.delete(f"/api/closes/{close['close_id']}").status_code == 204
        resp = client.post(
            "/api/activities",
            json={
                "project_id": project["project_id"],
                "target_month": "2026-05",
                "category": "fuel",
                "item_name": "軽油",
                "quantity": 10.0,
                "unit": "L",
            },
        )
        assert resp.status_code == 201

    def test_site_cannot_close(self, site_client: TestClient):
        resp = site_client.post(
            "/api/closes",
            json={"project_id": "x", "target_month": "2026-05"},
        )
        assert resp.status_code == 403


class TestCopyPreviousMonth:
    def test_copy_creates_unapproved_copies(self, client: TestClient):
        project = make_project(client)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=500.0, unit="L", target_month="2026-05", approved=True)
        resp = client.post(
            "/api/activities/copy-previous",
            json={"project_id": project["project_id"], "from_month": "2026-05", "to_month": "2026-06"},
        )
        assert resp.status_code == 200
        assert resp.json()["copied"] == 1
        activities = client.get(
            f"/api/activities?project_id={project['project_id']}&target_month=2026-06"
        ).json()
        assert activities[0]["approved"] is False
        assert activities[0]["source_file"] == "前月コピー: 2026-05"

    def test_copy_skips_duplicates(self, client: TestClient):
        project = make_project(client)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=500.0, unit="L", target_month="2026-05")
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=100.0, unit="L", target_month="2026-06")
        resp = client.post(
            "/api/activities/copy-previous",
            json={"project_id": project["project_id"], "from_month": "2026-05", "to_month": "2026-06"},
        )
        assert resp.json()["copied"] == 0
        assert resp.json()["skipped"] == 1


class TestReminders:
    def test_reminders_list(self, client: TestClient):
        project = make_project(client)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=10.0, unit="L", target_month="2026-06")
        resp = client.get("/api/emissions/reminders?target_month=2026-06")
        assert resp.status_code == 200
        items = resp.json()
        assert any(i["project_id"] == project["project_id"] and i["status"] == "unapproved" for i in items)

    def test_remind_creates_notifications(self, client: TestClient):
        make_project(client)
        resp = client.post(
            "/api/notifications/remind",
            json={"target_month": "2026-06"},
        )
        assert resp.status_code == 200
        assert resp.json()["reminded_projects"] >= 1
        notifications = client.get("/api/notifications?unread_only=true").json()
        assert any("督促" in n["message"] for n in notifications)


class TestExport:
    def test_full_export_zip(self, client: TestClient):
        make_project(client)
        resp = client.get("/api/export/full")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert "projects.json" in names
        assert "users.json" in names
        assert "metadata.json" in names
        projects = zf.read("projects.json")
        assert b"project_id" in projects

    def test_viewer_cannot_export(self, viewer_client: TestClient):
        assert viewer_client.get("/api/export/full").status_code == 403


class TestActivityComments:
    def test_comment_crud(self, client: TestClient):
        project = make_project(client)
        activity = make_activity(client, project["project_id"])
        created = client.post(
            f"/api/activities/{activity['activity_id']}/comments",
            json={"content": "数量の根拠を確認したい"},
        )
        assert created.status_code == 201
        assert created.json()["author"] == "admin"

        listed = client.get(f"/api/activities/{activity['activity_id']}/comments")
        assert len(listed.json()) == 1
        assert listed.json()[0]["content"] == "数量の根拠を確認したい"

        deleted = client.delete(
            f"/api/activities/{activity['activity_id']}/comments/{created.json()['comment_id']}"
        )
        assert deleted.status_code == 204

    def test_comment_notifies_reviewer(self, client_pair):
        admin, reviewer, _ = client_pair
        project = make_project(admin)
        activity = make_activity(admin, project["project_id"])
        admin.post(
            f"/api/activities/{activity['activity_id']}/comments",
            json={"content": "根拠を確認"},
        )
        notifications = reviewer.get("/api/notifications?unread_only=true").json()
        assert any("コメント" in n["message"] for n in notifications)


class TestUnitConversion:
    def test_convert_volume(self, client: TestClient):
        resp = client.post(
            "/api/units/convert",
            json={"value": 2.5, "from_unit": "kL", "to_unit": "L"},
        )
        assert resp.status_code == 200
        assert resp.json()["converted_value"] == pytest.approx(2500.0)

    def test_dimension_mismatch(self, client: TestClient):
        resp = client.post(
            "/api/units/convert",
            json={"value": 1.0, "from_unit": "t", "to_unit": "L"},
        )
        assert resp.status_code == 400

    def test_list_units(self, client: TestClient):
        resp = client.get("/api/units")
        units = {u["unit"] for u in resp.json()}
        assert {"L", "kL", "t", "kg", "kWh", "t-km"} <= units


class TestSupplierFactor:
    def test_supplier_specific_factor_used(self, client: TestClient):
        project = make_project(client)
        make_emission_factor(client, category="power", item_name="電力", unit="kWh",
                             factor_value=0.434, effective_from="2026-01-01")
        client.post("/api/factors", json={
            "category": "power", "item_name": "電力", "unit": "kWh",
            "factor_value": 0.500, "effective_from": "2026-01-01",
            "source": "東京電力EP", "supplier": "東京電力EP",
        })
        client.post(
            "/api/activities",
            json={
                "project_id": project["project_id"],
                "target_month": "2026-05",
                "category": "power",
                "item_name": "電力",
                "quantity": 1000.0,
                "unit": "kWh",
                "supplier": "東京電力EP",
            },
        )
        activity = client.get(
            f"/api/activities?project_id={project['project_id']}&target_month=2026-05"
        ).json()[0]
        client.put(f"/api/activities/{activity['activity_id']}/approve", json={"approved": True})
        resp = client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        assert resp.status_code == 200
        assert resp.json()[0]["factor_value"] == pytest.approx(0.500)
        assert resp.json()[0]["co2_kg"] == pytest.approx(500.0)


class TestProjectCard:
    def test_project_card_pdf(self, client: TestClient):
        project = make_project(client)
        make_emission_factor(client, category="fuel", item_name="軽油", unit="L", factor_value=2.58)
        make_activity(client, project["project_id"], category="fuel", item_name="軽油",
                      quantity=100.0, unit="L", target_month="2026-05", approved=True)
        client.post(
            "/api/emissions/calculate",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        resp = client.get(f"/api/reports/card/{project['project_id']}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"


class TestBranches:
    def test_branch_crud(self, client: TestClient):
        created = client.post("/api/branches", json={"name": "新潟支店"})
        assert created.status_code == 201
        branches = client.get("/api/branches").json()
        assert any(b["name"] == "新潟支店" for b in branches)
        assert client.delete(f"/api/branches/{created.json()['branch_id']}").status_code == 204

    def test_site_branch_restriction(self, client_pair):
        admin, _, site = client_pair
        osaka = admin.post(
            "/api/projects",
            json={
                "name": "大阪工事",
                "branch": "大阪支店",
                "work_type": "土木工事",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        ).json()
        resp = site.post(
            "/api/activities",
            json={
                "project_id": osaka["project_id"],
                "target_month": "2026-05",
                "category": "fuel",
                "item_name": "軽油",
                "quantity": 10.0,
                "unit": "L",
            },
        )
        assert resp.status_code == 403

        tokyo = admin.post(
            "/api/projects",
            json={
                "name": "東京工事",
                "branch": "東京支店",
                "work_type": "土木工事",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        ).json()
        projects = site.get("/api/projects").json()
        assert {p["project_id"] for p in projects} == {tokyo["project_id"]}


class TestTelematics:
    def test_simulator_import(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("MIRAI_TELEMATICS_MODE", "simulator")
        project = make_project(client)
        resp = client.post(
            "/api/telematics/import",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "simulator"
        assert data["imported"] >= 1
        activities = client.get(
            f"/api/activities?project_id={project['project_id']}&target_month=2026-05"
        ).json()
        assert any(a["category"] == "machine" for a in activities)

    def test_disabled_mode(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("MIRAI_TELEMATICS_MODE", "disabled")
        project = make_project(client)
        resp = client.post(
            "/api/telematics/import",
            json={"project_id": project["project_id"], "target_month": "2026-05"},
        )
        assert resp.status_code == 400


class TestClientPortal:
    def _create_client(self, client: TestClient, username: str) -> str:
        created = client.post(
            "/api/users",
            json={
                "username": username,
                "password": "client123",
                "display_name": "発注者",
                "role": "client",
            },
        ).json()
        return created["user_id"]

    def test_client_sees_only_assigned_projects(self, client: TestClient):
        from starlette.testclient import TestClient as TC

        from app.main import app as fastapi_app

        assigned = make_project(client)
        unassigned = make_project(client)
        user_id = self._create_client(client, "client_user")
        client.put(
            f"/api/users/{user_id}/projects",
            json={"user_id": user_id, "project_ids": [assigned["project_id"]]},
        )

        portal = TC(fastapi_app)
        login = portal.post(
            "/api/auth/login",
            json={"username": "client_user", "password": "client123"},
        )
        assert login.status_code == 200
        portal.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})

        projects = portal.get("/api/projects").json()
        assert {p["project_id"] for p in projects} == {assigned["project_id"]}
        assert portal.get(f"/api/projects/{unassigned['project_id']}").status_code == 403
        assert portal.post(
            "/api/activities",
            json={
                "project_id": assigned["project_id"],
                "target_month": "2026-05",
                "category": "fuel",
                "item_name": "軽油",
                "quantity": 10.0,
                "unit": "L",
            },
        ).status_code == 403

    def test_client_dashboard_filtered(self, client: TestClient):
        from starlette.testclient import TestClient as TC

        from app.main import app as fastapi_app

        assigned = make_project(client)
        make_project(client)
        user_id = self._create_client(client, "client_dash")
        client.put(
            f"/api/users/{user_id}/projects",
            json={"user_id": user_id, "project_ids": [assigned["project_id"]]},
        )
        portal = TC(fastapi_app)
        login = portal.post(
            "/api/auth/login",
            json={"username": "client_dash", "password": "client123"},
        )
        portal.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})
        dash = portal.get("/api/emissions/dashboard").json()
        assert dash["project_count"] == 1
