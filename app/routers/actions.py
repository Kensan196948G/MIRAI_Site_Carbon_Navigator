
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
    if project_id and not crud.has_project_access(db, user, project_id):
        raise HTTPException(status_code=403, detail="Project access denied")
    actions = crud.list_reduction_actions(
        db, project_id=project_id, target_month=target_month, status=status
    )
    if project_id is None:
        allowed = set(crud.project_ids_for_user(db, user))
        actions = [a for a in actions if a.project_id in allowed]
    return actions


@router.post("", response_model=schemas.ReductionActionRead, status_code=201)
def create_action(
    body: schemas.ReductionActionCreate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("site")),
):
    if not crud.get_project(db, body.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        crud.ensure_project_mutation_allowed(db, user, body.project_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return crud.create_reduction_action(db, body, user.username)


@router.put("/{action_id}", response_model=schemas.ReductionActionRead)
def update_action(
    action_id: str,
    body: schemas.ReductionActionUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("site")),
):
    existing = crud.get_reduction_action(db, action_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Reduction action not found")
    try:
        crud.ensure_project_mutation_allowed(db, user, existing.project_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return crud.update_reduction_action(db, action_id, body, user.username)


@router.delete("/{action_id}", status_code=204)
def delete_action(
    action_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("reviewer")),
):
    action = crud.get_reduction_action(db, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Reduction action not found")
    try:
        crud.ensure_project_mutation_allowed(db, user, action.project_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    crud.delete_reduction_action(db, action_id, user.username)
