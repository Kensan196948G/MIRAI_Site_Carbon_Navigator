"""PoC demo data generator: 2 construction sites x monthly activities."""
import datetime
import random

from sqlalchemy.orm import Session

from .. import crud, schemas
from .calculator import calculate_all_for_month

DEMO_PREFIX = "【デモ】"

DEMO_PROJECTS = [
    {
        "name": "【デモ】MIRAI港湾護岸工事",
        "branch": "東京支店",
        "work_type": "港湾工事",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "description": "PoC用デモデータ（港湾工事）",
    },
    {
        "name": "【デモ】MIRAI道路改良工事",
        "branch": "大阪支店",
        "work_type": "道路工事",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "description": "PoC用デモデータ（道路工事）",
    },
]

DEMO_MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]

DEMO_FACTORS = [
    ("fuel", "軽油", "L", 2.58),
    ("power", "電力", "kWh", 0.434),
    ("material", "鋼材", "t", 2000.0),
    ("transport", "一般輸送", "t-km", 0.172),
    ("machine", "油圧ショベル", "h", 18.5),
    ("waste", "建設廃棄物", "t", 45.0),
    ("business_travel", "出張(鉄道)", "人-km", 0.021),
    ("water", "上水道", "m3", 0.36),
    ("ship", "作業船", "h", 120.0),
]


def _ensure_demo_factors(db: Session, actor: str) -> None:
    for category, item_name, unit, factor_value in DEMO_FACTORS:
        if crud.get_latest_factor(db, category, item_name, unit):
            continue
        crud.create_emission_factor(
            db,
            schemas.EmissionFactorCreate(
                category=category,
                item_name=item_name,
                unit=unit,
                factor_value=factor_value,
                effective_from=datetime.date(2025, 1, 1),
                source="PoCデモデータ用",
            ),
            actor=actor,
        )


def _quantity(rng: random.Random, base: float, trend: float, month_idx: int, noise: float = 0.15) -> float:
    value = base * (1.0 + trend * month_idx) * rng.uniform(1.0 - noise, 1.0 + noise)
    return round(max(value, 0.1), 2)


def generate_demo_data(db: Session, actor: str) -> dict:
    existing = [
        p for p in crud.list_projects(db)
        if p.name.startswith(DEMO_PREFIX)
    ]
    if existing:
        return _summary(db, existing)

    _ensure_demo_factors(db, actor)

    rng = random.Random(42)
    projects = []
    total_activities = 0
    total_actions = 0
    total_feedbacks = 0

    for spec in DEMO_PROJECTS:
        project = crud.create_project(
            db,
            schemas.ProjectCreate(
                name=spec["name"],
                branch=spec["branch"],
                work_type=spec["work_type"],
                start_date=datetime.date.fromisoformat(spec["start_date"]),
                end_date=datetime.date.fromisoformat(spec["end_date"]),
                description=spec["description"],
                created_by=actor,
            ),
            actor=actor,
        )
        projects.append(project)

        monthly_plan = [
            ("fuel", "軽油", "L", 1800.0, 0.02),
            ("power", "電力", "kWh", 3200.0, 0.01),
            ("material", "鋼材", "t", 8.0, 0.05),
            ("transport", "一般輸送", "t-km", 1400.0, 0.03),
            ("machine", "油圧ショベル", "h", 220.0, 0.015),
            ("waste", "建設廃棄物", "t", 6.0, 0.02),
            ("business_travel", "出張(鉄道)", "人-km", 900.0, 0.0),
            ("water", "上水道", "m3", 160.0, 0.005),
        ]
        if spec["work_type"] == "港湾工事":
            monthly_plan.append(("ship", "作業船", "h", 140.0, 0.01))

        for month_idx, month in enumerate(DEMO_MONTHS):
            for category, item, unit, base, trend in monthly_plan:
                qty = _quantity(rng, base, trend, month_idx)
                activity = crud.create_activity_data(
                    db,
                    schemas.ActivityDataCreate(
                        project_id=project.project_id,
                        target_month=month,
                        category=category,
                        item_name=item,
                        quantity=qty,
                        unit=unit,
                        source_file="PoCデモデータ",
                        note="デモ用自動生成データ",
                        created_by=actor,
                    ),
                    actor=actor,
                )
                crud.approve_activity(db, activity.activity_id, True, actor)
                total_activities += 1
            calculate_all_for_month(db, project.project_id, month)

        # Reduction actions (site feedback loop demo)
        actions = [
            ("fuel", "待機時間削減による燃料消費低減", "implemented", 1200.0, 900.0),
            ("transport", "近隣調達による輸送距離短縮", "planned", 800.0, None),
            ("power", "LED照明・高効率機器への更新", "planned", 300.0, None),
        ]
        for category, suggestion, status, estimated, actual in actions:
            crud.create_reduction_action(
                db,
                schemas.ReductionActionCreate(
                    project_id=project.project_id,
                    target_month=DEMO_MONTHS[-1],
                    category=category,
                    suggestion=suggestion,
                    status=status,
                    estimated_reduction_kg=estimated,
                    actual_reduction_kg=actual,
                    note="PoCデモデータ",
                ),
                actor=actor,
            )
            total_actions += 1

        feedbacks = [
            ("fuel", "現場待機が多く、アイドリング時間の削減余地あり"),
            ("transport", "生コン運搬の混載化を検討してほしい"),
        ]
        for category, content in feedbacks:
            crud.create_site_feedback(
                db,
                schemas.SiteFeedbackCreate(
                    project_id=project.project_id,
                    target_month=DEMO_MONTHS[-1],
                    category=category,
                    content=content,
                ),
                actor=actor,
            )
            total_feedbacks += 1

    result = {
        "project_count": len(projects),
        "activity_count": total_activities,
        "result_count": len(crud.get_results_by_project(db)),
        "action_count": total_actions,
        "feedback_count": total_feedbacks,
        "projects": [p.name for p in projects],
    }
    return result


def clear_demo_data(db: Session, actor: str) -> int:
    demos = [p for p in crud.list_projects(db) if p.name.startswith(DEMO_PREFIX)]
    for project in demos:
        crud.delete_project(db, project.project_id, actor)
    return len(demos)


def demo_status(db: Session) -> dict:
    demos = [p for p in crud.list_projects(db) if p.name.startswith(DEMO_PREFIX)]
    return _summary(db, demos)


def _summary(db: Session, projects) -> dict:
    activity_count = sum(
        len(crud.list_activity_data(db, project_id=p.project_id))
        for p in projects
    )
    action_count = sum(
        len(crud.list_reduction_actions(db, project_id=p.project_id))
        for p in projects
    )
    feedback_count = sum(
        len(crud.list_site_feedbacks(db, project_id=p.project_id))
        for p in projects
    )
    return {
        "project_count": len(projects),
        "activity_count": activity_count,
        "result_count": len(crud.get_results_by_project(db)),
        "action_count": action_count,
        "feedback_count": feedback_count,
        "projects": [p.name for p in projects],
    }
