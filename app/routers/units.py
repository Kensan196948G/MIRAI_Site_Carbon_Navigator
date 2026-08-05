from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..security import get_current_user
from ..services import units as unit_service

router = APIRouter(prefix="/api/units", tags=["units"])


@router.get("")
def list_units(user=Depends(get_current_user)):
    return unit_service.list_units()


@router.post("/convert", response_model=schemas.UnitConvertResult)
def convert(
    body: schemas.UnitConvertRequest,
    user=Depends(get_current_user),
):
    try:
        return unit_service.convert(body.value, body.from_unit, body.to_unit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
