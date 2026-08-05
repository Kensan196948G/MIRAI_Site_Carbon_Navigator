from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..security import get_current_user
from ..services.assistant import assistant_suggestions

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.get("/suggestions", response_model=list[schemas.AssistantSuggestion])
def suggestions(
    project_id: str,
    target_month: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not crud.has_project_access(db, user, project_id):
        raise HTTPException(status_code=403, detail="Project access denied")
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return assistant_suggestions(db, project, target_month)
