
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..security import get_current_user, require_at_least

router = APIRouter(prefix="/api/actions", tags=["reduction-actions"])


@router.get("", response_model=list[schemas.ReductionActionRead])
def list_actions(
    project_id: str | None = None,
    target_month: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return crud.list_reduction_actions(
        db, project_id=project_id, target_month=target_month, status=status
    )


@router.post("", response_model=schemas.ReductionActionRead, status_code=201)
def create_action(
    body: schemas.ReductionActionCreate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("site")),
):
    if not crud.get_project(db, body.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return crud.create_reduction_action(db, body, user.username)


@router.put("/{action_id}", response_model=schemas.ReductionActionRead)
def update_action(
    action_id: str,
    body: schemas.ReductionActionUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("site")),
):
    action = crud.update_reduction_action(db, action_id, body, user.username)
    if not action:
        raise HTTPException(status_code=404, detail="Reduction action not found")
    return action


@router.delete("/{action_id}", status_code=204)
def delete_action(
    action_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("reviewer")),
):
    if not crud.delete_reduction_action(db, action_id, user.username):
        raise HTTPException(status_code=404, detail="Reduction action not found")
