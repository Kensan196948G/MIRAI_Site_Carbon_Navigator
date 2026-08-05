from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..security import require_at_least

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[schemas.UserRead])
def list_users(
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    return crud.list_users(db)


@router.post("", response_model=schemas.UserRead, status_code=201)
def create_user(
    body: schemas.UserCreate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    if body.role not in {"admin", "reviewer", "site", "viewer"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    try:
        return crud.create_user(db, body, actor=user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{user_id}/active", response_model=schemas.UserRead)
def set_active(
    user_id: str,
    is_active: bool,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    result = crud.set_user_active(db, user_id, is_active, user.username)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return result


@router.put("/{user_id}", response_model=schemas.UserRead)
def update_user(
    user_id: str,
    body: schemas.UserUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    if body.role is not None and body.role not in {"admin", "reviewer", "site", "viewer"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    result = crud.update_user(db, user_id, body, user.username)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return result
