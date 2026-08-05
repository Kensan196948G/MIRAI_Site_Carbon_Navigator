from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..security import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[schemas.NotificationRead])
def list_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return crud.list_notifications(db, user, unread_only=unread_only)


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return {"count": crud.unread_notification_count(db, user)}


@router.put("/{notification_id}/read", status_code=204)
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not crud.mark_notification_read(db, notification_id, user):
        raise HTTPException(status_code=404, detail="Notification not found")


@router.put("/read-all", status_code=204)
def mark_all_read(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    crud.mark_all_notifications_read(db, user)
