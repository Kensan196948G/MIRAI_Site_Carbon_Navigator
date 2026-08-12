import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

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
    _create_indexes()


def _create_indexes():
    """Create the indexes used by the most common query paths.

    Uses IF NOT EXISTS so this is safe on both SQLite and PostgreSQL and
    remains idempotent across app restarts.
    """
    statements = [
        "CREATE INDEX IF NOT EXISTS ix_activity_data_project_month ON activity_data (project_id, target_month)",
        "CREATE INDEX IF NOT EXISTS ix_activity_data_project ON activity_data (project_id)",
        "CREATE INDEX IF NOT EXISTS ix_activity_data_month ON activity_data (target_month)",
        "CREATE INDEX IF NOT EXISTS ix_activity_data_approved ON activity_data (approved)",
        "CREATE INDEX IF NOT EXISTS ix_emission_results_activity ON emission_results (activity_id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_created ON audit_logs (created_at)",
        "CREATE INDEX IF NOT EXISTS ix_notifications_recipient ON notifications (recipient_role, recipient_username)",
        "CREATE INDEX IF NOT EXISTS ix_user_project_access_user ON user_project_access (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_emission_factors_lookup ON emission_factors (category, item_name, unit)",
        "CREATE INDEX IF NOT EXISTS ix_monthly_closes_lookup ON monthly_closes (project_id, target_month)",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


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
                "approval_status": "ALTER TABLE activity_data ADD COLUMN approval_status VARCHAR DEFAULT 'draft'",
            }.items():
                if col not in columns:
                    conn.execute(text(ddl))

    if "offset_credits" in tables:
        columns = {c["name"] for c in inspector.get_columns("offset_credits")}
        with engine.begin() as conn:
            if "allocated_tco2" not in columns:
                conn.execute(text("ALTER TABLE offset_credits ADD COLUMN allocated_tco2 FLOAT DEFAULT 0"))

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
            if "totp_secret" not in columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN totp_secret VARCHAR"))
            if "is_2fa_enabled" not in columns:
                default = "false" if dialect == "postgresql" else "0"
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN is_2fa_enabled BOOLEAN DEFAULT "
                        + default
                    )
                )
            if "oidc_sub" not in columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN oidc_sub VARCHAR"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
