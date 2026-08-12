"""
Seed initial emission factors with real Japanese emission data.
Run: python seed_data.py
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app import crud, schemas
from app.database import SessionLocal, create_tables
from app.models import Branch, User
from app.security import hash_password


def seed():
    create_tables()
    db = SessionLocal()

    factors = [
        # Fuel
        {"category": "fuel", "item_name": "軽油", "unit": "L", "factor_value": 2.58, "source": "環境省 排出係数"},
        {"category": "fuel", "item_name": "A重油", "unit": "L", "factor_value": 2.71, "source": "環境省 排出係数"},
        {"category": "fuel", "item_name": "ガソリン", "unit": "L", "factor_value": 2.32, "source": "環境省 排出係数"},
        {"category": "fuel", "item_name": "LPG", "unit": "kg", "factor_value": 3.00, "source": "環境省 排出係数"},
        # Power
        {"category": "power", "item_name": "電力", "unit": "kWh", "factor_value": 0.434, "source": "環境省 排出係数 (全国平均)"},
        {"category": "power", "item_name": "電力", "unit": "kWh", "factor_value": 0.421, "source": "東京電力EP 2024年度調整後排出係数(速報値)", "supplier": "東京電力EP"},
        {"category": "power", "item_name": "電力", "unit": "kWh", "factor_value": 0.409, "source": "関西電力 排出係数 (目安)", "supplier": "関西電力"},
        {"category": "power", "item_name": "電力", "unit": "kWh", "factor_value": 0.428, "source": "中部電力 排出係数 (目安)", "supplier": "中部電力"},
        # Material
        {"category": "material", "item_name": "鋼材", "unit": "t", "factor_value": 2000.0, "source": "環境省 排出係数"},
        {"category": "material", "item_name": "コンクリート", "unit": "t", "factor_value": 300.0, "source": "環境省 排出係数"},
        {"category": "material", "item_name": "生コン", "unit": "t", "factor_value": 300.0, "source": "環境省 排出係数"},
        {"category": "material", "item_name": "セメント", "unit": "t", "factor_value": 750.0, "source": "環境省 排出係数"},
        {"category": "material", "item_name": "アスファルト", "unit": "t", "factor_value": 200.0, "source": "環境省 排出係数"},
        # Transport
        {"category": "transport", "item_name": "一般輸送", "unit": "t-km", "factor_value": 0.172, "source": "環境省 排出係数 (トラック輸送)"},
        {"category": "transport", "item_name": "船舶輸送", "unit": "t-km", "factor_value": 0.039, "source": "環境省 排出係数 (内航海運)"},
        {"category": "machine", "item_name": "油圧ショベル", "unit": "h", "factor_value": 18.5, "source": "建機メーカーカタログ値 (目安)"},
        {"category": "machine", "item_name": "クローラクレーン", "unit": "h", "factor_value": 32.0, "source": "建機メーカーカタログ値 (目安)"},
        {"category": "ship", "item_name": "作業船", "unit": "h", "factor_value": 120.0, "source": "内航船排出原単位 (目安)"},
        {"category": "waste", "item_name": "建設廃棄物", "unit": "t", "factor_value": 45.0, "source": "廃棄物処理原単位 (目安)"},
        {"category": "business_travel", "item_name": "出張(鉄道)", "unit": "人-km", "factor_value": 0.021, "source": "環境省 排出係数 (鉄道)"},
        {"category": "business_travel", "item_name": "出張(飛行機)", "unit": "人-km", "factor_value": 0.095, "source": "環境省 排出係数 (航空)"},
        {"category": "commuting", "item_name": "通勤(車)", "unit": "人-km", "factor_value": 0.130, "source": "環境省 排出係数 (乗用車)"},
        {"category": "water", "item_name": "上水道", "unit": "m3", "factor_value": 0.360, "source": "水道排出原単位 (目安)"},
    ]

    added = 0
    skipped = 0
    for f in factors:
        existing = crud.list_emission_factors(db, category=f["category"])
        already_exists = any(
            e.item_name == f["item_name"]
            and e.unit == f["unit"]
            and (e.supplier or None) == (f.get("supplier") or None)
            for e in existing
        )
        if already_exists:
            skipped += 1
            continue
        factor_create = schemas.EmissionFactorCreate(
            category=f["category"],
            item_name=f["item_name"],
            unit=f["unit"],
            factor_value=f["factor_value"],
            effective_from=datetime.date(2026, 1, 1),
            source=f["source"],
            supplier=f.get("supplier"),
        )
        crud.create_emission_factor(db, factor_create)
        added += 1

    # Default users are development-only. Production deployments set
    # MIRAI_SEED_DEFAULT_USERS=0 and provide MIRAI_INITIAL_ADMIN_PASSWORD.
    seed_default_users = os.getenv("MIRAI_SEED_DEFAULT_USERS", "1") == "1"
    users_added = 0
    if seed_default_users:
        default_users = [
            ("admin", "CarbonAdmin", "admin", "admin123", None, "admin@example.local"),
            ("reviewer", "環境レビュアー", "reviewer", "reviewer123", None, "reviewer@example.local"),
            ("site", "現場入力担当", "site", "site123", "東京支店", "site@example.local"),
            ("viewer", "閲覧ユーザー", "viewer", "viewer123", None, "viewer@example.local"),
        ]
        for username, display_name, role, password, branch, email in default_users:
            if crud.get_user_by_username(db, username):
                continue
            db_user = User(
                user_id=str(__import__("uuid").uuid4()),
                username=username,
                display_name=display_name,
                password_hash=hash_password(password),
                role=role,
                branch=branch,
                email=email,
                is_active=True,
                created_at=datetime.datetime.now(datetime.UTC),
            )
            db.add(db_user)
            users_added += 1
    else:
        # Production bootstrap: create the first admin from environment variables
        # when no admin account exists yet.
        admin_exists = (
            db.query(User).filter(User.role == "admin", User.is_active == True).first()  # noqa: E712
            is not None
        )
        if not admin_exists:
            initial_password = os.getenv("MIRAI_INITIAL_ADMIN_PASSWORD", "")
            if len(initial_password) < 12:
                raise SystemExit(
                    "MIRAI_INITIAL_ADMIN_PASSWORD is required (min 12 chars) when "
                    "MIRAI_SEED_DEFAULT_USERS=0 and no admin account exists"
                )
            username = os.getenv("MIRAI_INITIAL_ADMIN_USERNAME", "admin").lower()
            display = os.getenv("MIRAI_INITIAL_ADMIN_DISPLAY_NAME", "初期管理者")
            email = os.getenv("MIRAI_INITIAL_ADMIN_EMAIL", "") or None
            db_user = User(
                user_id=str(__import__("uuid").uuid4()),
                username=username,
                display_name=display,
                password_hash=hash_password(initial_password),
                role="admin",
                email=email,
                is_active=True,
                created_at=datetime.datetime.now(datetime.UTC),
            )
            db.add(db_user)
            users_added += 1
    db.commit()

    # Default branches
    branches_added = 0
    for name in ["東京支店", "大阪支店", "東北支店", "九州支店"]:
        if db.query(Branch).filter(Branch.name == name).first():
            continue
        db.add(Branch(
            branch_id=str(__import__("uuid").uuid4()),
            name=name,
            created_at=datetime.datetime.now(datetime.UTC),
        ))
        branches_added += 1
    db.commit()

    db.close()
    print(
        f"Seed complete: {added} factors added, {skipped} skipped "
        f"(already exist), {users_added} users added, {branches_added} branches added"
    )


if __name__ == "__main__":
    seed()
