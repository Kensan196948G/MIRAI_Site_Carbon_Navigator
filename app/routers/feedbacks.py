
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..security import get_current_user, require_at_least

router = APIRouter(prefix="/api/feedbacks", tags=["site-feedbacks"])


@router.get("", response_model=list[schemas.SiteFeedbackRead])
def list_feedbacks(
    project_id: str | None = None,
    target_month: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if project_id and not crud.has_project_access(db, user, project_id):
        raise HTTPException(status_code=403, detail="Project access denied")
    feedbacks = crud.list_site_feedbacks(
        db, project_id=project_id, target_month=target_month, status=status
    )
    if project_id is None:
        allowed = set(crud.project_ids_for_user(db, user))
        feedbacks = [f for f in feedbacks if f.project_id in allowed]
    return feedbacks


@router.post("", response_model=schemas.SiteFeedbackRead, status_code=201)
def create_feedback(
    body: schemas.SiteFeedbackCreate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("site")),
):
    if not crud.get_project(db, body.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        crud.ensure_project_mutation_allowed(db, user, body.project_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return crud.create_site_feedback(db, body, user.username)


@router.put("/{feedback_id}", response_model=schemas.SiteFeedbackRead)
def update_feedback(
    feedback_id: str,
    body: schemas.SiteFeedbackUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("site")),
):
    if body.status is not None and body.status not in {"open", "acknowledged", "resolved"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    existing = crud.get_site_feedback(db, feedback_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Feedback not found")
    try:
        crud.ensure_project_mutation_allowed(db, user, existing.project_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return crud.update_site_feedback(db, feedback_id, body, user.username)


@router.delete("/{feedback_id}", status_code=204)
def delete_feedback(
    feedback_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("reviewer")),
):
    feedback = crud.get_site_feedback(db, feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    try:
        crud.ensure_project_mutation_allowed(db, user, feedback.project_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    crud.delete_site_feedback(db, feedback_id, user.username)
