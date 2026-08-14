"""
Operability check for the MVP demo dataset.

Verifies that a freshly seeded demo environment can be logged into and that
the major review workflows (dashboard, SBTi, credits, closes, notifications,
anomalies, missing factors, client portal, branch isolation) are populated.

Usage:
    DATABASE_URL=sqlite:///./mvp_data/mirai_carbon_mvp.db \
        python scripts/verify_mvp_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _login(client: TestClient, username: str, password: str) -> dict:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"login failed for {username}: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def main() -> None:
    client = TestClient(app)

    ready = client.get("/api/health/ready")
    assert ready.status_code == 200, ready.text
    meta = client.get("/api/meta").json()
    assert meta["demo_mode"] is True, meta
    assert meta["environment"] == "development", meta

    admin = _login(client, "demo_admin", "DemoAdmin!2026")
    client.headers.update(admin)

    dashboard = client.get("/api/emissions/dashboard").json()
    assert dashboard["project_count"] == 2, dashboard
    assert dashboard["total_co2_t"] > 0, dashboard

    projects = client.get("/api/projects").json()
    assert len(projects) == 2
    harbor = next(p for p in projects if "港湾" in p["name"])

    assert len(client.get("/api/sbti/targets").json()) == 3
    credits = client.get("/api/credits").json()
    assert len(credits) >= 3
    credit_summary = client.get("/api/credits/summary").json()
    assert credit_summary["total_tco2"] > 0

    assert len(client.get("/api/closes").json()) >= 2
    assert len(client.get("/api/notifications").json()) >= 1
    assert len(client.get("/api/audit-logs?limit=100").json()) > 10

    anomalies = client.get(
        f"/api/emissions/anomalies?project_id={harbor['project_id']}&target_month=2026-04"
    ).json()
    assert any("A重油" in a["item_name"] for a in anomalies), anomalies

    missing = client.get(
        f"/api/emissions/missing-factors?project_id={harbor['project_id']}&target_month=2026-06"
    ).json()
    assert any("試験用特殊鋼材" in m["item_name"] for m in missing), missing

    # Reviewer receives role-wide activity notifications plus demo guidance.
    client.headers.clear()
    client.headers.update(_login(client, "demo_reviewer", "DemoReviewer!2026"))
    assert len(client.get("/api/notifications").json()) >= 2

    # Client portal: assigned to both demo projects, read-only.
    client.headers.clear()
    client.headers.update(_login(client, "demo_client", "DemoClient!2026"))
    client_projects = client.get("/api/projects").json()
    assert len(client_projects) == 2
    assert client.get("/api/factors").status_code == 403

    # Branch isolation: Tokyo site sees only Tokyo projects, never Osaka by ID.
    client.headers.clear()
    client.headers.update(_login(client, "demo_site_tokyo", "DemoSiteTokyo!2026"))
    tokyo_projects = client.get("/api/projects").json()
    assert len(tokyo_projects) == 1
    assert all(p["branch"] == "東京支店" for p in tokyo_projects)
    osaka = next(p for p in projects if "道路" in p["name"])
    assert client.get(f"/api/projects/{osaka['project_id']}").status_code == 403
    assert (
        client.get(f"/api/activities?project_id={osaka['project_id']}").status_code == 403
    )

    # Multi-stage approval demo data exists in 2026-08.
    workflow = client.get(
        f"/api/activities?project_id={harbor['project_id']}&target_month=2026-08"
    ).json()
    statuses = {a["approval_status"] for a in workflow}
    assert {"draft", "site_submitted", "branch_approved"} <= statuses, statuses

    print("MVP demo verification: PASS")


if __name__ == "__main__":
    main()
