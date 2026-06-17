from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from .. import crud, schemas
from ..database import get_db

router = APIRouter(prefix="/api/factors", tags=["factors"])


@router.post("", response_model=schemas.EmissionFactorRead, status_code=201)
def create_factor(factor: schemas.EmissionFactorCreate, db: Session = Depends(get_db)):
    return crud.create_emission_factor(db, factor)


@router.get("", response_model=list[schemas.EmissionFactorRead])
def list_factors(category: Optional[str] = None, db: Session = Depends(get_db)):
    return crud.list_emission_factors(db, category=category)


@router.get("/{factor_id}", response_model=schemas.EmissionFactorRead)
def get_factor(factor_id: str, db: Session = Depends(get_db)):
    factor = crud.get_emission_factor(db, factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail="Emission factor not found")
    return factor
