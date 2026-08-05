import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./carbon_navigator.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def create_tables():
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns():
    """Lightweight additive migration for SQLite (existing DBs from MVP)."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    dialect = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect == "postgresql" else "DATETIME"

    # activity_data: approver + edit audit columns
    if "activity_data" in tables:
        columns = {c["name"] for c in inspector.get_columns("activity_data")}
        with engine.begin() as conn:
            for col, ddl in {
                "approved_by": "ALTER TABLE activity_data ADD COLUMN approved_by VARCHAR",
                "approved_at": f"ALTER TABLE activity_data ADD COLUMN approved_at {datetime_type}",
                "updated_by": "ALTER TABLE activity_data ADD COLUMN updated_by VARCHAR",
                "updated_at": f"ALTER TABLE activity_data ADD COLUMN updated_at {datetime_type}",
                "note": "ALTER TABLE activity_data ADD COLUMN note VARCHAR",
                "supplier": "ALTER TABLE activity_data ADD COLUMN supplier VARCHAR",
            }.items():
                if col not in columns:
                    conn.execute(text(ddl))

    # emission_results: factor snapshot columns
    if "emission_results" in tables:
        columns = {c["name"] for c in inspector.get_columns("emission_results")}
        with engine.begin() as conn:
            for col, ddl in {
                "factor_value": "ALTER TABLE emission_results ADD COLUMN factor_value FLOAT",
                "factor_source": "ALTER TABLE emission_results ADD COLUMN factor_source VARCHAR",
                "factor_effective_from": "ALTER TABLE emission_results ADD COLUMN factor_effective_from DATE",
                "item_name": "ALTER TABLE emission_results ADD COLUMN item_name VARCHAR",
                "unit": "ALTER TABLE emission_results ADD COLUMN unit VARCHAR",
            }.items():
                if col not in columns:
                    conn.execute(text(ddl))

    # projects: audit columns
    if "projects" in tables:
        columns = {c["name"] for c in inspector.get_columns("projects")}
        with engine.begin() as conn:
            if "close_day" not in columns:
                conn.execute(text("ALTER TABLE projects ADD COLUMN close_day INTEGER"))
            if "updated_at" not in columns:
                conn.execute(text(f"ALTER TABLE projects ADD COLUMN updated_at {datetime_type}"))
            if "updated_by" not in columns:
                conn.execute(text("ALTER TABLE projects ADD COLUMN updated_by VARCHAR"))

    # emission_factors: audit columns
    if "emission_factors" in tables:
        columns = {c["name"] for c in inspector.get_columns("emission_factors")}
        with engine.begin() as conn:
            if "created_by" not in columns:
                conn.execute(text("ALTER TABLE emission_factors ADD COLUMN created_by VARCHAR"))
            if "supplier" not in columns:
                conn.execute(text("ALTER TABLE emission_factors ADD COLUMN supplier VARCHAR"))
            if "updated_at" not in columns:
                conn.execute(text(f"ALTER TABLE emission_factors ADD COLUMN updated_at {datetime_type}"))
            if "updated_by" not in columns:
                conn.execute(text("ALTER TABLE emission_factors ADD COLUMN updated_by VARCHAR"))

    if "users" in tables:
        columns = {c["name"] for c in inspector.get_columns("users")}
        with engine.begin() as conn:
            if "branch" not in columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN branch VARCHAR"))
            if "email" not in columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
