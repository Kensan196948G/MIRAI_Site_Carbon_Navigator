"""
Pytest configuration and shared fixtures for MIRAI Site Carbon Navigator tests.

Important: SQLite in-memory databases are per-connection by default. We use
StaticPool so that every SQLAlchemy session shares the same underlying
sqlite3 connection, which ensures that tables created with create_all()
are visible to the dependency-overridden sessions during requests.
"""
import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.main import app as fastapi_app
from app.database import Base, get_db
from app.models import Branch, User
from app.security import hash_password
import app.models  # noqa: F401 — ensures all ORM models are registered with Base.metadata


# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------

def _make_client(role: str):
    """
    Create a fresh in-memory SQLite database and an authenticated TestClient.
    Overrides the get_db dependency so the app uses the test DB.

    StaticPool is required so that all sessions (including those created
    inside FastAPI request handlers) share the same SQLite connection and
    therefore see the same tables and data.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create all tables in the shared in-memory connection
    Base.metadata.create_all(bind=engine)

    # Seed default users so role-protected endpoints can be exercised.
    session = TestingSessionLocal()
    for username, display_name, user_role, branch in [
        ("admin", "管理者", "admin", None),
        ("reviewer", "レビュアー", "reviewer", None),
        ("site", "現場担当", "site", "東京支店"),
        ("viewer", "閲覧者", "viewer", None),
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
                created_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
    session.commit()
    for name in ["東京支店", "大阪支店", "東北支店"]:
        session.add(Branch(
            branch_id=f"branch-{name}",
            name=name,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        ))
    session.commit()
    session.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db

    with TestClient(fastapi_app) as test_client:
        login_resp = test_client.post(
            "/api/auth/login",
            json={"username": role, "password": f"{role}123"},
        )
        assert login_resp.status_code == 200, login_resp.text
        token = login_resp.json()["access_token"]
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client

    # Cleanup
    fastapi_app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client():
    yield from _make_client("admin")


@pytest.fixture(scope="function")
def viewer_client():
    yield from _make_client("viewer")


@pytest.fixture(scope="function")
def site_client():
    yield from _make_client("site")


@pytest.fixture(scope="function")
def reviewer_client():
    yield from _make_client("reviewer")


@pytest.fixture(scope="function")
def client_pair():
    """Admin and reviewer clients sharing one in-memory DB (for notification tests)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    for username, display_name, user_role, branch in [
        ("admin", "管理者", "admin", None),
        ("reviewer", "レビュアー", "reviewer", None),
        ("site", "現場担当", "site", "東京支店"),
        ("viewer", "閲覧者", "viewer", None),
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
                created_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
    session.commit()
    for name in ["東京支店", "大阪支店", "東北支店"]:
        session.add(Branch(
            branch_id=f"branch-{name}",
            name=name,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        ))
    session.commit()
    session.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db

    def login(username, password):
        client = TestClient(fastapi_app)
        resp = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 200, resp.text
        client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
        return client

    with TestClient(fastapi_app) as admin:
        login_resp = admin.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert login_resp.status_code == 200, login_resp.text
        admin.headers.update({"Authorization": f"Bearer {login_resp.json()['access_token']}"})
        reviewer = login("reviewer", "reviewer123")
        site = login("site", "site123")
        yield admin, reviewer, site

    fastapi_app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Helper factory functions
# ---------------------------------------------------------------------------

def make_project(client: TestClient, project_id_hint: str = "proj-001") -> dict:
    """Create a project and return the response JSON."""
    payload = {
        "name": f"MIRAI港湾工事 ({project_id_hint})",
        "branch": "東北支店",
        "work_type": "土木工事",
        "start_date": "2026-04-01",
        "end_date": "2026-09-30",
        "description": "テスト用プロジェクト",
        "created_by": "test_user",
    }
    resp = client.post("/api/projects", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_emission_factor(
    client: TestClient,
    category: str = "fuel",
    item_name: str = "軽油",
    unit: str = "L",
    factor_value: float = 2.58,
    effective_from: str = "2025-01-01",
) -> dict:
    """Create an emission factor and return the response JSON."""
    payload = {
        "category": category,
        "item_name": item_name,
        "unit": unit,
        "factor_value": factor_value,
        "effective_from": effective_from,
        "source": "環境省排出係数一覧",
    }
    resp = client.post("/api/factors", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_activity(
    client: TestClient,
    project_id: str,
    category: str = "fuel",
    item_name: str = "軽油",
    quantity: float = 500.0,
    unit: str = "L",
    target_month: str = "2026-05",
    approved: bool = False,
) -> dict:
    """Create an activity (and optionally approve it). Returns the response JSON."""
    payload = {
        "project_id": project_id,
        "target_month": target_month,
        "category": category,
        "item_name": item_name,
        "quantity": quantity,
        "unit": unit,
        "source_file": None,
        "created_by": "test_user",
    }
    resp = client.post("/api/activities", json=payload)
    assert resp.status_code == 201, resp.text
    activity = resp.json()

    if approved:
        approve_resp = client.put(
            f"/api/activities/{activity['activity_id']}/approve",
            json={"approved": True},
        )
        assert approve_resp.status_code == 200, approve_resp.text
        activity = approve_resp.json()

    return activity
