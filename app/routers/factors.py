from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from .. import crud, schemas
from ..database import get_db
from ..security import get_current_user, require_at_least

router = APIRouter(prefix="/api/factors", tags=["factors"])


@router.post("", response_model=schemas.EmissionFactorRead, status_code=201)
def create_factor(
    factor: schemas.EmissionFactorCreate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    return crud.create_emission_factor(db, factor, actor=user.username)


@router.get("", response_model=list[schemas.EmissionFactorRead])
def list_factors(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return crud.list_emission_factors(db, category=category)


@router.get("/{factor_id}", response_model=schemas.EmissionFactorRead)
def get_factor(
    factor_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    factor = crud.get_emission_factor(db, factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail="Emission factor not found")
    return factor


@router.put("/{factor_id}", response_model=schemas.EmissionFactorRead)
def update_factor(
    factor_id: str,
    body: schemas.EmissionFactorUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    factor = crud.update_emission_factor(db, factor_id, body, user.username)
    if not factor:
        raise HTTPException(status_code=404, detail="Emission factor not found")
    return factor


@router.delete("/{factor_id}", status_code=204)
def delete_factor(
    factor_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    if not crud.delete_emission_factor(db, factor_id, user.username):
        raise HTTPException(status_code=404, detail="Emission factor not found")
