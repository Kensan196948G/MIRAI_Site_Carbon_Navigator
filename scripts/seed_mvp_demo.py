"""
MVP/Prototype demo dataset seed for MIRAI Site Carbon Navigator.

Creates an idempotent, fully-fictional demo dataset so reviewers can operate
every major workflow immediately: multi-stage approvals, monthly closes,
notifications, comments, SBTi targets, offset credits, client portal access,
anomalies and missing-factor warnings.

Usage:
    python scripts/seed_mvp_demo.py

The script never touches production data: it works against the DATABASE_URL
provided by the environment (default: ./mvp_data/mirai_carbon_mvp.db).
All names, companies, e-mail addresses and amounts are fictitious.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import crud, models, schemas  # noqa: E402
from app.database import SessionLocal, create_tables  # noqa: E402
from app.services import demo as demo_service  # noqa: E402
from app.services.calculator import calculate_all_for_month  # noqa: E402

# Development-only demo accounts. These are dummy credentials for the MVP
# review environment and must never be used in production.
DEMO_USERS = [
    {
        "username": "demo_admin",
        "password": "DemoAdmin!2026",
        "display_name": "デモ管理者（架空）",
        "role": "admin",
        "branch": None,
        "email": "demo.admin@example.com",
    },
    {
        "username": "demo_reviewer",
        "password": "DemoReviewer!2026",
        "display_name": "デモ環境レビュアー（架空）",
        "role": "reviewer",
        "branch": None,
        "email": "demo.reviewer@example.com",
    },
    {
        "username": "demo_site_tokyo",
        "password": "DemoSiteTokyo!2026",
        "display_name": "デモ現場担当・東京（架空）",
        "role": "site",
        "branch": "東京支店",
        "email": "demo.site.tokyo@example.com",
    },
    {
        "username": "demo_site_osaka",
        "password": "DemoSiteOsaka!2026",
        "display_name": "デモ現場担当・大阪（架空）",
        "role": "site",
        "branch": "大阪支店",
        "email": "demo.site.osaka@example.com",
    },
    {
        "username": "demo_client",
        "password": "DemoClient!2026",
        "display_name": "デモ発注者（架空）",
        "role": "client",
        "branch": None,
        "email": "demo.client@example.com",
    },
]

SBTI_TARGETS = [
    {
        "scope": "scope1",
        "name": "Scope1 直接排出 42% 削減（デモ目標）",
        "description": "燃料・建機・船舶の排出削減。架空のデモ目標。",
        "base_year": 2025,
        "target_year": 2030,
        "base_emissions_kg": 520_000.0,
        "reduction_percent": 42.0,
    },
    {
        "scope": "scope2",
        "name": "Scope2 電力 42% 削減（デモ目標）",
        "description": "再エネ電力調達・高効率機器更新。架空のデモ目標。",
        "base_year": 2025,
        "target_year": 2030,
        "base_emissions_kg": 85_000.0,
        "reduction_percent": 42.0,
    },
    {
        "scope": "scope3",
        "name": "Scope3 その他間接 25% 削減（デモ目標）",
        "description": "材料・輸送・廃棄物・出張・通勤・水。架空のデモ目標。",
        "base_year": 2025,
        "target_year": 2030,
        "base_emissions_kg": 210_000.0,
        "reduction_percent": 25.0,
    },
]

CREDITS = [
    {
        "credit_type": "j_credit",
        "name": "J-クレジット（デモ）",
        "serial_number": "DEMO-JCR-2026-0001",
        "quantity_tco2": 50.0,
        "purchased_at": datetime.date(2026, 4, 1),
        "note": "架空のデモ用クレジット",
        "allocate_to_project": None,
        "retire": False,
    },
    {
        "credit_type": "certificate",
        "name": "再エネ証書（デモ）",
        "serial_number": "DEMO-RE100-2026-0002",
        "quantity_tco2": 20.0,
        "purchased_at": datetime.date(2026, 5, 1),
        "note": "架空のデモ用再エネ証書",
        "allocate_to_project": None,
        "retire": True,
    },
    {
        "credit_type": "j_credit",
        "name": "J-クレジット 港湾工事充当分（デモ）",
        "serial_number": "DEMO-JCR-2026-0003",
        "quantity_tco2": 30.0,
        "purchased_at": datetime.date(2026, 6, 1),
        "note": "架空のデモ用クレジット（工事充当デモ）",
        "allocate_to_project": 0,
        "retire": False,
    },
]


def _ensure_demo_users(db) -> None:
    created = 0
    for spec in DEMO_USERS:
        if crud.get_user_by_username(db, spec["username"]):
            continue
        crud.create_user(
            db,
            schemas.UserCreate(
                username=spec["username"],
                password=spec["password"],
                display_name=spec["display_name"],
                role=spec["role"],
                branch=spec["branch"],
                email=spec["email"],
            ),
            actor="seed_mvp_demo",
        )
        created += 1
    return created


def _ensure_sbti_targets(db, actor: str) -> int:
    if crud.list_sbti_targets(db):
        return 0
    created = 0
    for spec in SBTI_TARGETS:
        crud.create_sbti_target(
            db,
            schemas.SbtiTargetCreate(
                scope=spec["scope"],
                name=spec["name"],
                description=spec["description"],
                base_year=spec["base_year"],
                target_year=spec["target_year"],
                base_emissions_kg=spec["base_emissions_kg"],
                reduction_percent=spec["reduction_percent"],
            ),
            actor=actor,
        )
        created += 1
    return created


def _ensure_credits(db, projects, actor: str) -> int:
    if crud.list_offset_credits(db):
        return 0
    created = 0
    for spec in CREDITS:
        credit = crud.create_offset_credit(
            db,
            schemas.OffsetCreditCreate(
                credit_type=spec["credit_type"],
                name=spec["name"],
                serial_number=spec["serial_number"],
                quantity_tco2=spec["quantity_tco2"],
                purchased_at=spec["purchased_at"],
                note=spec["note"],
            ),
            actor=actor,
        )
        if spec["allocate_to_project"] is not None and projects:
            crud.allocate_offset_credit(
                db,
                credit.credit_id,
                projects[spec["allocate_to_project"]].project_id,
                12.0,
                actor,
            )
        if spec["retire"]:
            crud.retire_offset_credit(db, credit.credit_id, actor)
        created += 1
    return created


def _ensure_client_access(db, projects, actor: str) -> int:
    client = crud.get_user_by_username(db, "demo_client")
    if not client:
        return 0
    existing = (
        db.query(models.UserProjectAccess)
        .filter(models.UserProjectAccess.user_id == client.user_id)
        .count()
    )
    if existing or not projects:
        return 0
    crud.set_user_project_access(
        db,
        client.user_id,
        [p.project_id for p in projects],
        actor,
    )
    return len(projects)


def _ensure_monthly_closes(db, projects, actor: str) -> int:
    created = 0
    for project in projects:
        if crud.is_month_closed(db, project.project_id, "2026-03"):
            continue
        crud.create_monthly_close(
            db,
            schemas.MonthlyCloseCreate(
                project_id=project.project_id,
                target_month="2026-03",
                note="デモ用月次締め（架空データ）",
            ),
            actor=actor,
        )
        created += 1
    return created


def _ensure_workflow_demo_activities(db, project, actor: str) -> int:
    """Add activities that demonstrate draft / submitted / branch-approved states,
    an anomaly, and a missing-factor warning."""
    created = 0
    existing_keys = {
        (a.category, a.item_name, a.unit, a.target_month)
        for a in crud.list_activity_data(db, project_id=project.project_id)
    }

    def add(category: str, item: str, unit: str, qty: float, month: str, note: str):
        nonlocal created
        key = (category, item, unit, month)
        if key in existing_keys:
            return None
        activity = crud.create_activity_data(
            db,
            schemas.ActivityDataCreate(
                project_id=project.project_id,
                target_month=month,
                category=category,
                item_name=item,
                quantity=qty,
                unit=unit,
                source_file="デモ用ワークフロー検証",
                note=note,
            ),
            actor=actor,
        )
        existing_keys.add(key)
        created += 1
        return activity

    # 1) draft: reviewer sees an unsubmitted activity.
    add("fuel", "軽油", "L", 1500.0, "2026-08", "未提出（下書き）のデモ活動量")

    # 2) site_submitted: branch reviewer can approve this.
    submitted = add("power", "電力", "kWh", 3200.0, "2026-08", "支店承認待ちのデモ活動量")
    if submitted:
        crud.transition_approval(db, submitted.activity_id, "submit", actor)

    # 3) branch_approved: environment reviewer can complete the chain.
    branch = add("machine", "油圧ショベル", "h", 190.0, "2026-08", "環境部承認待ちのデモ活動量")
    if branch:
        crud.transition_approval(db, branch.activity_id, "submit", actor)
        crud.transition_approval(db, branch.activity_id, "approve_branch", actor)

    # 4) Anomaly: A重油 jumps from 100 L (2026-03) to 20,000 L (2026-04).
    for month, qty in [("2026-03", 100.0), ("2026-04", 20_000.0)]:
        anomaly = add("fuel", "A重油", "L", qty, month, "異常値検知デモ（前月比200倍）")
        if anomaly:
            crud.approve_activity(db, anomaly.activity_id, True, actor)
            calculate_all_for_month(db, project.project_id, month)

    # 5) Missing factor: no emission factor is registered for this item.
    missing = add(
        "material",
        "試験用特殊鋼材",
        "t",
        3.5,
        "2026-06",
        "係数未設定のデモ活動量（未算定表示の確認用）",
    )
    if missing:
        crud.approve_activity(db, missing.activity_id, True, actor)
    return created


def _ensure_notifications(db) -> int:
    already = (
        db.query(models.Notification)
        .filter(
            models.Notification.recipient_role == "admin",
            models.Notification.message.like("【デモ】MVPデモデータ%"),
        )
        .first()
    )
    if already:
        return 0
    samples = [
        {
            "role": "admin",
            "username": None,
            "message": "【デモ】MVPデモデータが生成されました。各画面を操作できます",
            "link": "/#/dashboard",
        },
        {
            "role": None,
            "username": "demo_reviewer",
            "message": "【デモ】支店承認待ちの活動量があります（2026-08）",
            "link": "/#/activities",
        },
        {
            "role": None,
            "username": "demo_site_tokyo",
            "message": "【デモ】2026-08 の活動量入力が未完了です",
            "link": "/#/activities",
        },
        {
            "role": None,
            "username": "demo_site_osaka",
            "message": "【デモ】2026-03 は締め済みです（デモデータ）",
            "link": "/#/reports",
        },
        {
            "role": None,
            "username": "demo_client",
            "message": "【デモ】発注者ポータルへようこそ。割当工事のレポートを閲覧できます",
            "link": "/#/reports",
        },
    ]
    for sample in samples:
        crud.add_notification(
            db,
            message=sample["message"],
            recipient_role=sample["role"],
            recipient_username=sample["username"],
            link=sample["link"],
        )
    return len(samples)


def main() -> None:
    create_tables()
    import seed_data  # noqa: PLC0415 - applied after create_tables()

    seed_data.seed()
    db = SessionLocal()
    try:
        actor = "demo_admin"
        demo_result = demo_service.generate_demo_data(db, actor)
        projects = [
            p for p in crud.list_projects(db)
            if p.name.startswith(demo_service.DEMO_PREFIX)
        ]
        users_added = _ensure_demo_users(db)
        targets_added = _ensure_sbti_targets(db, actor)
        credits_added = _ensure_credits(db, projects, actor)
        access_added = _ensure_client_access(db, projects, actor)
        closes_added = _ensure_monthly_closes(db, projects, actor)
        workflow_added = sum(
            _ensure_workflow_demo_activities(db, p, actor) for p in projects
        )
        notifications_added = _ensure_notifications(db)
        db.commit()

        print("MVP demo seed complete:")
        print(f"  projects={demo_result['project_count']} "
              f"activities={demo_result['activity_count'] + workflow_added} "
              f"results={demo_result['result_count']}")
        print(f"  users_added={users_added} sbti_targets={targets_added} "
              f"credits={credits_added} client_access={access_added}")
        print(f"  closes={closes_added} workflow_activities={workflow_added} "
              f"notifications={notifications_added}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
