from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..security import get_current_user, require_at_least

router = APIRouter(prefix="/api/credits", tags=["credits"])


@router.get("", response_model=list[schemas.OffsetCreditRead])
def list_credits(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return crud.list_offset_credits(db, status=status)


@router.get("/summary", response_model=schemas.OffsetSummary)
def credit_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return crud.offset_summary(db)


@router.post("", response_model=schemas.OffsetCreditRead, status_code=201)
def create_credit(
    body: schemas.OffsetCreditCreate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    try:
        return crud.create_offset_credit(db, body, user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{credit_id}/allocate", response_model=schemas.OffsetCreditRead)
def allocate_credit(
    credit_id: str,
    body: schemas.OffsetAllocateRequest,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("reviewer")),
):
    if not crud.get_project(db, body.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return crud.allocate_offset_credit(
            db, credit_id, body.project_id, body.quantity_tco2, user.username
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{credit_id}/retire", response_model=schemas.OffsetCreditRead)
def retire_credit(
    credit_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    try:
        return crud.retire_offset_credit(db, credit_id, user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{credit_id}", status_code=204)
def delete_credit(
    credit_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    if not crud.delete_offset_credit(db, credit_id, user.username):
        raise HTTPException(status_code=404, detail="Credit not found")
