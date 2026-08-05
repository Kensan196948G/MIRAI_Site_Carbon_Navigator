from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..security import require_at_least

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@router.get("", response_model=list[schemas.AuditLogRead])
def list_logs(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user=Depends(require_at_least("reviewer")),
):
    return crud.list_audit_logs(db, limit=limit)
