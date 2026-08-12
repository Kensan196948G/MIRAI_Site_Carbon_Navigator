
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..security import get_current_user, require_at_least

router = APIRouter(prefix="/api/closes", tags=["monthly-closes"])


@router.get("", response_model=list[schemas.MonthlyCloseRead])
def list_closes(
    project_id: str | None = None,
    target_month: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    closes = crud.list_monthly_closes(db, project_id=project_id, target_month=target_month)
    if project_id is None:
        allowed = set(crud.project_ids_for_user(db, user))
        closes = [c for c in closes if c.project_id in allowed]
    return closes


@router.post("", response_model=schemas.MonthlyCloseRead, status_code=201)
def close_month(
    body: schemas.MonthlyCloseCreate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("reviewer")),
):
    if not crud.get_project(db, body.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        crud.ensure_project_mutation_allowed(db, user, body.project_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    try:
        return crud.create_monthly_close(db, body, user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{close_id}", status_code=204)
def delete_close(
    close_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    close = (
        db.query(models.MonthlyClose)
        .filter(models.MonthlyClose.close_id == close_id)
        .first()
    )
    if not close:
        raise HTTPException(status_code=404, detail="Close record not found")
    if not crud.delete_monthly_close(db, close_id, user.username):
        raise HTTPException(status_code=404, detail="Close record not found")
