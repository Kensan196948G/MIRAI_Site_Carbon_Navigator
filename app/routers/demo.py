from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..security import get_current_user, require_at_least
from ..services.demo import clear_demo_data, demo_status, generate_demo_data

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/status", response_model=schemas.DemoGenerateResult)
def status(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return demo_status(db)


@router.post("/generate", response_model=schemas.DemoGenerateResult, status_code=201)
def generate(
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    return generate_demo_data(db, user.username)


@router.delete("/clear", response_model=dict)
def clear(
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    removed = clear_demo_data(db, user.username)
    return {"removed": removed}
