from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..security import get_current_user, require_at_least

router = APIRouter(prefix="/api/branches", tags=["branches"])


@router.get("", response_model=list[schemas.BranchRead])
def list_branches(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return crud.list_branches(db)


@router.post("", response_model=schemas.BranchRead, status_code=201)
def create_branch(
    body: schemas.BranchCreate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    try:
        return crud.create_branch(db, body.name.strip(), user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{branch_id}", status_code=204)
def delete_branch(
    branch_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    if not crud.delete_branch(db, branch_id, user.username):
        raise HTTPException(status_code=404, detail="Branch not found")
