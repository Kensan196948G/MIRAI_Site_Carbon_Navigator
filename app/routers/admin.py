import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..security import require_at_least
from ..services.notify import send_email, send_teams
from ..version import __version__

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/status")
def ops_status(
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    return {
        "version": __version__,
        "db": db_status,
        "uptime_seconds": round(time.time() - _start_time),
        "users": len(crud.list_users(db)),
        "projects": len(crud.list_projects(db)),
        "activities": len(crud.list_activity_data(db)),
        "results": len(crud.get_results_by_project(db)),
    }


@router.post("/notify-test")
def notify_test(
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    """Send a test notification to configured SMTP/Teams channels."""
    email_sent = send_email(
        [u.email for u in crud.list_users(db) if u.email and u.role == "admin"],
        "[MIRAI Carbon Navigator] 通知試験",
        f"通知試験メッセージ（{user.username} 実行 / {time.strftime('%Y-%m-%d %H:%M:%S')}）",
    )
    teams_sent = send_teams("✅ MIRAI Carbon Navigator 通知試験")
    return {
        "email_sent": email_sent,
        "teams_sent": teams_sent,
        "note": "email_sent/teams_sent が false の場合は該当チャネルが未設定",
    }


_start_time = time.time()
