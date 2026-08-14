"""Regression tests for production-hardening changes.

Covers: static asset serving, project-scoped data isolation (site branch /
client portal), TOTP-secret-free exports, login throttling, approval-chain
enforcement, approval-state reset on edit, project-delete cascades, seed
behaviour in production mode, and OIDC code exchange (no token in URL).
"""
import datetime
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

import app.main  # noqa: F401 - establishes the canonical import order
import app.models  # noqa: F401
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models import Branch, User
from app.routers import auth as auth_router
from app.security import hash_password


@pytest.fixture()
def _clear_login_state():
    auth_router._login_failures.clear()
    auth_router._oidc_states.clear()
    auth_router._oidc_codes.clear()
    yield
    auth_router._login_failures.clear()
    auth_router._oidc_states.clear()
    auth_router._oidc_codes.clear()


def _fresh_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    for username, display_name, user_role, branch in [
        ("admin", "管理者", "admin", None),
        ("reviewer", "レビュアー", "reviewer", None),
        ("site_tokyo", "現場(東京)", "site", "東京支店"),
        ("client1", "発注者1", "client", None),
    ]:
        session.add(
            User(
                user_id=f"user-{username}",
                username=username,
                display_name=display_name,
                password_hash=hash_password(f"{username}123"),
                role=user_role,
                branch=branch,
                email=f"{username}@example.local",
                is_active=True,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
    for name in ["東京支店", "大阪支店"]:
        session.add(
            Branch(
                branch_id=f"branch-{name}",
                name=name,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
    session.commit()
    session.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    return SessionLocal


@pytest.fixture()
def app_env(_clear_login_state):
    SessionLocal = _fresh_engine()
    yield SessionLocal
    fastapi_app.dependency_overrides.clear()


def _login(SessionLocal, username: str) -> TestClient:
    client = TestClient(fastapi_app)
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": f"{username}123"},
    )
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


def _seed_projects_and_activity(SessionLocal, admin: TestClient) -> dict:
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
    admin.post(
        "/api/factors",
        json={
            "category": "fuel",
            "item_name": "軽油",
            "unit": "L",
            "factor_value": 2.58,
            "effective_from": "2026-01-01",
            "source": "test",
        },
    )
    osaka_activity = admin.post(
        "/api/activities",
        json={
            "project_id": osaka["project_id"],
            "target_month": "2026-05",
            "category": "fuel",
            "item_name": "軽油",
            "quantity": 1000,
            "unit": "L",
        },
    ).json()
    tokyo_activity = admin.post(
        "/api/activities",
        json={
            "project_id": tokyo["project_id"],
            "target_month": "2026-05",
            "category": "fuel",
            "item_name": "軽油",
            "quantity": 100,
            "unit": "L",
        },
    ).json()
    return {
        "tokyo": tokyo,
        "osaka": osaka,
        "osaka_activity": osaka_activity,
        "tokyo_activity": tokyo_activity,
    }


class TestStaticAssets:
    def test_frontend_assets_are_served(self, app_env):
        admin = _login(app_env, "admin")
        for path in [
            "/",
            "/static/css/style.css",
            "/static/js/app.js",
            "/static/favicon.svg",
            "/favicon.ico",
            "/static/vendor/bootstrap.min.css",
            "/static/vendor/bootstrap.bundle.min.js",
            "/static/vendor/chart.umd.min.js",
            "/static/vendor/bootstrap-icons/bootstrap-icons.min.css",
            "/static/vendor/bootstrap-icons/fonts/bootstrap-icons.woff2",
        ]:
            assert admin.get(path).status_code == 200, path

    def test_no_cdn_scripts_allowed_by_csp(self, app_env):
        admin = _login(app_env, "admin")
        csp = admin.get("/").headers["content-security-policy"]
        assert "cdn.jsdelivr.net" not in csp

    def test_csp_allows_inline_handlers_and_cloudflare_beacon(self, app_env):
        admin = _login(app_env, "admin")
        csp = admin.get("/").headers["content-security-policy"]
        # Inline onclick handlers (static SPA buttons) must keep working.
        assert "script-src-attr 'unsafe-inline'" in csp
        # Cloudflare Web Analytics beacon is explicitly allowed.
        assert "https://static.cloudflareinsights.com" in csp
        assert "https://cloudflareinsights.com" in csp

    def test_favicon_is_linked(self, app_env):
        admin = _login(app_env, "admin")
        index = admin.get("/").text
        assert "/static/favicon.svg" in index


class TestProjectIsolation:
    def test_site_sees_only_own_branch_in_unfiltered_lists(self, app_env):
        admin = _login(app_env, "admin")
        site = _login(app_env, "site_tokyo")
        projects = _seed_projects_and_activity(app_env, admin)
        admin.put(f"/api/activities/{projects['osaka_activity']['activity_id']}/approve", json={"approved": True})
        admin.post(
            "/api/emissions/calculate",
            json={"project_id": projects["osaka"]["project_id"], "target_month": "2026-05"},
        )

        activities = site.get("/api/activities").json()
        assert {a["project_id"] for a in activities} == {projects["tokyo"]["project_id"]}

        results = site.get("/api/emissions/results").json()
        assert len(results) == 0

        reminders = site.get("/api/emissions/reminders?target_month=2026-05").json()
        assert {r["project_id"] for r in reminders} == {projects["tokyo"]["project_id"]}

    def test_site_cannot_mutate_other_branch(self, app_env):
        admin = _login(app_env, "admin")
        site = _login(app_env, "site_tokyo")
        projects = _seed_projects_and_activity(app_env, admin)

        assert site.put(
            f"/api/activities/{projects['osaka_activity']['activity_id']}",
            json={"quantity": 999},
        ).status_code == 403
        assert site.delete(
            f"/api/activities/{projects['osaka_activity']['activity_id']}"
        ).status_code == 403
        assert site.post(
            "/api/activities",
            json={
                "project_id": projects["osaka"]["project_id"],
                "target_month": "2026-05",
                "category": "fuel",
                "item_name": "軽油",
                "quantity": 1,
                "unit": "L",
            },
        ).status_code == 403

    def test_site_cannot_submit_other_branch_activity(self, app_env):
        admin = _login(app_env, "admin")
        site = _login(app_env, "site_tokyo")
        projects = _seed_projects_and_activity(app_env, admin)
        resp = site.put(
            f"/api/activities/{projects['osaka_activity']['activity_id']}/approval",
            json={"action": "submit"},
        )
        assert resp.status_code == 403

    def test_site_excel_import_forces_own_branch(self, app_env):
        import io

        from openpyxl import Workbook

        site = _login(app_env, "site_tokyo")
        wb = Workbook()
        ws = wb.active
        ws.append(["name", "branch", "work_type", "start_date", "end_date", "description", "close_day"])
        ws.append(["東京持ち込み工事", "大阪支店", "土木工事", "2026-01-01", "2026-12-31", None, None])
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        resp = site.post(
            "/api/projects/import",
            files={"file": ("projects.xlsx", buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        assert resp.json()["imported"] == 1
        projects = site.get("/api/projects").json()
        imported = [p for p in projects if p["name"] == "東京持ち込み工事"]
        assert len(imported) == 1
        assert imported[0]["branch"] == "東京支店"

    def test_client_sees_only_assigned_projects_and_no_corporate_data(self, app_env):
        admin = _login(app_env, "admin")
        client = _login(app_env, "client1")
        projects = _seed_projects_and_activity(app_env, admin)
        admin.put(
            "/api/users/user-client1/projects",
            json={"user_id": "user-client1", "project_ids": [projects["tokyo"]["project_id"]]},
        )

        assert client.get(f"/api/projects/{projects['osaka']['project_id']}").status_code == 403
        activities = client.get("/api/activities").json()
        assert {a["project_id"] for a in activities} == {projects["tokyo"]["project_id"]}
        assert client.get("/api/activities").json()

        # Project-scoped data is visible for assigned projects only...
        assert client.get("/api/actions").status_code == 200
        assert client.get("/api/feedbacks").status_code == 200
        # ...while corporate master data is internal-only.
        for path in ["/api/credits", "/api/credits/summary",
                     "/api/sbti/targets", "/api/sbti/progress", "/api/factors"]:
            assert client.get(path).status_code == 403, path

        # Client cannot mutate anything even on an assigned project.
        resp = client.post(
            "/api/activities",
            json={
                "project_id": projects["tokyo"]["project_id"],
                "target_month": "2026-05",
                "category": "fuel",
                "item_name": "軽油",
                "quantity": 1,
                "unit": "L",
            },
        )
        assert resp.status_code == 403


class TestSiteCrossBranchReadIsolation:
    """Regression: site users must not read another branch via explicit project_id."""

    def test_site_cannot_read_other_branch_with_explicit_project_id(self, app_env):
        admin = _login(app_env, "admin")
        site = _login(app_env, "site_tokyo")
        projects = _seed_projects_and_activity(app_env, admin)
        osaka_id = projects["osaka"]["project_id"]
        osaka_activity_id = projects["osaka_activity"]["activity_id"]
        tokyo_id = projects["tokyo"]["project_id"]

        admin.post(
            "/api/actions",
            json={
                "project_id": osaka_id,
                "target_month": "2026-05",
                "category": "fuel",
                "suggestion": "デモ削減アクション",
                "status": "planned",
            },
        )
        admin.post(
            "/api/feedbacks",
            json={
                "project_id": osaka_id,
                "target_month": "2026-05",
                "category": "fuel",
                "content": "デモフィードバック",
            },
        )
        admin.post(
            "/api/closes",
            json={"project_id": osaka_id, "target_month": "2026-05"},
        )

        blocked_paths = [
            f"/api/projects/{osaka_id}",
            f"/api/activities?project_id={osaka_id}",
            f"/api/activities/{osaka_activity_id}/comments",
            f"/api/activities/{osaka_activity_id}/history",
            f"/api/emissions/results?project_id={osaka_id}",
            f"/api/emissions/summary?project_id={osaka_id}&target_month=2026-05",
            f"/api/emissions/trend?project_id={osaka_id}",
            f"/api/emissions/scope-summary?project_id={osaka_id}&target_month=2026-05",
            f"/api/emissions/benchmark?project_id={osaka_id}&target_month=2026-05",
            f"/api/emissions/anomalies?project_id={osaka_id}&target_month=2026-05",
            f"/api/emissions/missing-factors?project_id={osaka_id}&target_month=2026-05",
            f"/api/emissions/comparison?project_id={osaka_id}&target_month=2026-05",
            f"/api/emissions/forecast?project_id={osaka_id}",
            f"/api/assistant/suggestions?project_id={osaka_id}&target_month=2026-05",
            f"/api/reports/monthly/{osaka_id}/2026-05",
            f"/api/reports/card/{osaka_id}",
            f"/api/actions?project_id={osaka_id}",
            f"/api/feedbacks?project_id={osaka_id}",
            f"/api/closes?project_id={osaka_id}",
        ]
        for path in blocked_paths:
            assert site.get(path).status_code == 403, path

        # Positive control: the site user can still read own-branch data explicitly.
        assert site.get(f"/api/activities?project_id={tokyo_id}").status_code == 200
        assert site.get(f"/api/projects/{tokyo_id}").status_code == 200

    def test_created_site_user_keeps_branch_scoping(self, app_env):
        admin = _login(app_env, "admin")
        projects = _seed_projects_and_activity(app_env, admin)

        created = admin.post(
            "/api/users",
            json={
                "username": "site_osaka_new",
                "password": "SiteOsaka!2026",
                "display_name": "大阪新規担当",
                "role": "site",
                "branch": "大阪支店",
                "email": "site_osaka_new@example.local",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["branch"] == "大阪支店"

        client = TestClient(fastapi_app)
        resp = client.post(
            "/api/auth/login",
            json={"username": "site_osaka_new", "password": "SiteOsaka!2026"},
        )
        assert resp.status_code == 200, resp.text
        client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})

        # The new user sees only their assigned branch, even with explicit IDs.
        assert client.get(
            f"/api/projects/{projects['tokyo']['project_id']}"
        ).status_code == 403
        assert client.get(
            f"/api/activities?project_id={projects['tokyo']['project_id']}"
        ).status_code == 403
        assert client.get(
            f"/api/projects/{projects['osaka']['project_id']}"
        ).status_code == 200
        project_ids = {p["project_id"] for p in client.get("/api/projects").json()}
        assert project_ids == {projects["osaka"]["project_id"]}


class TestExportSecrets:
    def test_export_excludes_totp_and_password_hash(self, app_env):
        admin = _login(app_env, "admin")
        from app.models import User as UserModel

        session = app_env()
        user = session.query(UserModel).filter(UserModel.username == "admin").first()
        user.totp_secret = "TOPSECRETXYZ"
        session.commit()
        session.close()

        import io
        import zipfile

        resp = admin.get("/api/export/full")
        assert resp.status_code == 200
        archive = zipfile.ZipFile(io.BytesIO(resp.content))
        users = archive.read("users.json").decode()
        assert "TOPSECRETXYZ" not in users
        assert "password_hash" not in users


class TestLoginThrottling:
    def test_login_locked_after_repeated_failures(self, app_env, monkeypatch):
        auth_router._MAX_LOGIN_FAILURES = 3
        client = TestClient(fastapi_app)
        for _ in range(3):
            resp = client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "wrong"},
            )
            assert resp.status_code == 401
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers


class TestApprovalIntegrity:
    def test_approve_env_requires_branch_approval(self, app_env):
        admin = _login(app_env, "admin")
        reviewer = _login(app_env, "reviewer")
        site = _login(app_env, "site_tokyo")
        projects = _seed_projects_and_activity(app_env, admin)
        aid = projects["tokyo_activity"]["activity_id"]
        site.put(f"/api/activities/{aid}/approval", json={"action": "submit"})
        resp = reviewer.put(
            f"/api/activities/{aid}/approval", json={"action": "approve_env"}
        )
        assert resp.status_code == 400
        reviewer.put(f"/api/activities/{aid}/approval", json={"action": "approve_branch"})
        resp = reviewer.put(
            f"/api/activities/{aid}/approval", json={"action": "approve_env"}
        )
        assert resp.status_code == 200
        assert resp.json()["approval_status"] == "env_approved"

    def test_update_resets_approval_status_to_draft(self, app_env):
        admin = _login(app_env, "admin")
        reviewer = _login(app_env, "reviewer")
        site = _login(app_env, "site_tokyo")
        projects = _seed_projects_and_activity(app_env, admin)
        aid = projects["tokyo_activity"]["activity_id"]
        site.put(f"/api/activities/{aid}/approval", json={"action": "submit"})
        reviewer.put(f"/api/activities/{aid}/approval", json={"action": "approve_branch"})
        reviewer.put(f"/api/activities/{aid}/approval", json={"action": "approve_env"})
        assert admin.get(f"/api/activities?project_id={projects['tokyo']['project_id']}").json()[0]["approval_status"] == "env_approved"
        resp = site.put(f"/api/activities/{aid}", json={"quantity": 120})
        assert resp.status_code == 200
        data = resp.json()
        assert data["approved"] is False
        assert data["approval_status"] == "draft"


class TestProjectDeleteCascade:
    def test_delete_removes_related_rows_and_frees_credits(self, app_env):
        admin = _login(app_env, "admin")
        projects = _seed_projects_and_activity(app_env, admin)
        pid = projects["tokyo"]["project_id"]
        admin.post(
            "/api/closes",
            json={"project_id": pid, "target_month": "2026-05"},
        )
        credit = admin.post(
            "/api/credits",
            json={"credit_type": "j_credit", "name": "J-クレジット1", "quantity_tco2": 10},
        ).json()
        admin.post(f"/api/credits/{credit['credit_id']}/allocate", json={"project_id": pid, "quantity_tco2": 2})

        assert admin.delete(f"/api/projects/{pid}").status_code == 204
        assert admin.get(f"/api/projects/{pid}").status_code == 404
        from app import crud

        session = app_env()
        assert crud.get_results_by_project(session, project_id=pid) == []
        assert crud.list_monthly_closes(session, project_id=pid) == []
        assert crud.list_activity_data(session, project_id=pid) == []
        refreshed = crud.get_offset_credit(session, credit["credit_id"])
        assert refreshed.status == "available"
        assert refreshed.allocated_project_id is None
        session.close()


class TestSeedProductionMode:
    def test_production_seed_skips_defaults_and_requires_admin_password(self, app_env, monkeypatch):
        import seed_data

        monkeypatch.setattr(seed_data, "create_tables", lambda: None)
        monkeypatch.setattr(seed_data, "SessionLocal", app_env)
        session = app_env()
        session.query(User).delete()
        session.commit()
        session.close()
        monkeypatch.setenv("MIRAI_SEED_DEFAULT_USERS", "0")
        monkeypatch.delenv("MIRAI_INITIAL_ADMIN_PASSWORD", raising=False)
        with pytest.raises(SystemExit):
            seed_data.seed()

        session = app_env()
        session.query(User).delete()
        session.commit()
        session.close()
        monkeypatch.setenv("MIRAI_INITIAL_ADMIN_PASSWORD", "prod-admin-pass-123")
        monkeypatch.setenv("MIRAI_INITIAL_ADMIN_USERNAME", "prodadmin")
        seed_data.seed()
        session = app_env()
        assert session.query(User).filter(User.username == "admin").count() == 0
        assert session.query(User).filter(User.username == "prodadmin").count() == 1
        session.close()

    def test_dev_seed_keeps_defaults(self, app_env, monkeypatch):
        import seed_data

        monkeypatch.setattr(seed_data, "create_tables", lambda: None)
        monkeypatch.setattr(seed_data, "SessionLocal", app_env)
        session = app_env()
        session.query(User).delete()
        session.commit()
        session.close()
        monkeypatch.setenv("MIRAI_SEED_DEFAULT_USERS", "1")
        seed_data.seed()
        session = app_env()
        assert session.query(User).filter(User.username == "admin").count() == 1
        session.close()


class TestOidcCodeExchange:
    def test_callback_redirects_with_code_and_exchange_issues_token(
        self, app_env, monkeypatch
    ):
        from app.services import oidc

        monkeypatch.setattr(oidc, "oidc_enabled", lambda: True)
        monkeypatch.setattr(
            oidc,
            "login_with_code",
            lambda code: {"sub": "oidc-sub-xyz", "email": "external@example.com", "name": "外部ユーザー"},
        )
        monkeypatch.setenv("MIRAI_FRONTEND_URL", "http://frontend.test")
        auth_router._oidc_states["test-state"] = time.time() + 600

        client = TestClient(fastapi_app)
        resp = client.get(
            "/api/auth/oidc/callback?code=abc&state=test-state",
            follow_redirects=False,
        )
        assert resp.status_code == 307
        location = resp.headers["location"]
        assert "token=" not in location
        assert "code=" in location
        code = location.split("code=", 1)[1]

        exchange = client.post("/api/auth/oidc/exchange", json={"code": code})
        assert exchange.status_code == 200
        assert exchange.json()["access_token"]
        assert exchange.json()["user"]["username"] == "external"

        replay = client.post("/api/auth/oidc/exchange", json={"code": code})
        assert replay.status_code == 400
