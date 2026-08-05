"""
Seed initial emission factors with real Japanese emission data.
Run: python seed_data.py
"""
import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, create_tables
from app import crud, schemas
from app.security import hash_password
from app.models import User


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
    ]

    added = 0
    skipped = 0
    for f in factors:
        existing = crud.list_emission_factors(db, category=f["category"])
        already_exists = any(
            e.item_name == f["item_name"] and e.unit == f["unit"]
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
        )
        crud.create_emission_factor(db, factor_create)
        added += 1

    # Default users (development credentials — rotate before production)
    default_users = [
        ("admin", "CarbonAdmin", "admin", "admin123"),
        ("reviewer", "環境レビュアー", "reviewer", "reviewer123"),
        ("site", "現場入力担当", "site", "site123"),
        ("viewer", "閲覧ユーザー", "viewer", "viewer123"),
    ]
    users_added = 0
    for username, display_name, role, password in default_users:
        if crud.get_user_by_username(db, username):
            continue
        db_user = User(
            user_id=str(__import__("uuid").uuid4()),
            username=username,
            display_name=display_name,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(db_user)
        users_added += 1
    db.commit()

    db.close()
    print(
        f"Seed complete: {added} factors added, {skipped} skipped "
        f"(already exist), {users_added} users added"
    )


if __name__ == "__main__":
    seed()
