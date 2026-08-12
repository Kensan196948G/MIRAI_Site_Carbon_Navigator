from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..security import get_current_user, require_at_least
from ..services.sbti import compute_sbti_progress

router = APIRouter(prefix="/api/sbti", tags=["sbti"])


@router.get("/targets", response_model=list[schemas.SbtiTargetRead])
def list_targets(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if user.role == "client":
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return crud.list_sbti_targets(db)


@router.post("/targets", response_model=schemas.SbtiTargetRead, status_code=201)
def create_target(
    body: schemas.SbtiTargetCreate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    if body.scope not in {"scope1", "scope2", "scope3"}:
        raise HTTPException(status_code=400, detail="Invalid scope")
    return crud.create_sbti_target(db, body, user.username)


@router.put("/targets/{target_id}", response_model=schemas.SbtiTargetRead)
def update_target(
    target_id: str,
    body: schemas.SbtiTargetUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    target = crud.update_sbti_target(db, target_id, body, user.username)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


@router.delete("/targets/{target_id}", status_code=204)
def delete_target(
    target_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    if not crud.delete_sbti_target(db, target_id, user.username):
        raise HTTPException(status_code=404, detail="Target not found")


@router.get("/progress", response_model=list[schemas.SbtiProgressItem])
def progress(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if user.role == "client":
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return compute_sbti_progress(db)
