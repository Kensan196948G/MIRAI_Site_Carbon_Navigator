
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
    return crud.list_site_feedbacks(
        db, project_id=project_id, target_month=target_month, status=status
    )


@router.post("", response_model=schemas.SiteFeedbackRead, status_code=201)
def create_feedback(
    body: schemas.SiteFeedbackCreate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("site")),
):
    if not crud.get_project(db, body.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
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
    feedback = crud.update_site_feedback(db, feedback_id, body, user.username)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return feedback


@router.delete("/{feedback_id}", status_code=204)
def delete_feedback(
    feedback_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("reviewer")),
):
    if not crud.delete_site_feedback(db, feedback_id, user.username):
        raise HTTPException(status_code=404, detail="Feedback not found")
