import io
import json
import zipfile

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import crud, models
from ..database import get_db
from ..security import require_at_least

router = APIRouter(prefix="/api/export", tags=["export"])


def _rows_to_dicts(rows, exclude: set[str] | None = None):
    result = []
    for row in rows:
        data = {}
        for col in row.__table__.columns:
            key = col.name
            if exclude and key in exclude:
                continue
            value = getattr(row, key)
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            data[key] = value
        result.append(data)
    return result


@router.get("/full")
def export_full(
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    payload = {
        "exported_at": crud.utcnow().isoformat(),
        "exported_by": user.username,
        "projects": _rows_to_dicts(crud.list_projects(db)),
        "emission_factors": _rows_to_dicts(crud.list_emission_factors(db)),
        "activities": _rows_to_dicts(crud.list_activity_data(db)),
        "emission_results": _rows_to_dicts(crud.get_results_by_project(db)),
        "reduction_actions": _rows_to_dicts(crud.list_reduction_actions(db)),
        "site_feedbacks": _rows_to_dicts(crud.list_site_feedbacks(db)),
        "sbti_targets": _rows_to_dicts(crud.list_sbti_targets(db)),
        "monthly_closes": _rows_to_dicts(crud.list_monthly_closes(db)),
        "branches": _rows_to_dicts(crud.list_branches(db)),
        "audit_logs": _rows_to_dicts(crud.list_audit_logs(db, limit=10000)),
        "users": _rows_to_dicts(crud.list_users(db), exclude={"password_hash"}),
        "notifications": _rows_to_dicts(crud.list_notifications(db, user, limit=10000)),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for table, rows in payload.items():
            if table == "exported_at":
                continue
            zf.writestr(f"{table}.json", json.dumps(rows, ensure_ascii=False, indent=2))
        zf.writestr("metadata.json", json.dumps(
            {k: v for k, v in payload.items() if k in ("exported_at", "exported_by")},
            ensure_ascii=False,
            indent=2,
        ))
    buffer.seek(0)
    filename = f"mirai_carbon_export_{crud.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
