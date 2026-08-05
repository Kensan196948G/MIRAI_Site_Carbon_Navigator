from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import crud, schemas
from ..database import get_db
from ..security import get_current_user, require_at_least

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=schemas.ProjectRead, status_code=201)
def create_project(
    project: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("site")),
):
    if user.role == "site" and user.branch:
        project.branch = user.branch
    return crud.create_project(db, project, actor=user.username)


@router.get("", response_model=list[schemas.ProjectRead])
def list_projects(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return crud.list_projects_for_user(db, user)


@router.get("/{project_id}", response_model=schemas.ProjectRead)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not crud.has_project_access(db, user, project_id):
        raise HTTPException(status_code=403, detail="Project access denied")
    return project


@router.put("/{project_id}", response_model=schemas.ProjectRead)
def update_project(
    project_id: str,
    body: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("site")),
):
    existing = crud.get_project(db, project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    if user.role == "site" and user.branch and existing.branch != user.branch:
        raise HTTPException(status_code=403, detail="他支店の工事は変更できません")
    project = crud.update_project(db, project_id, body, user.username)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("admin")),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if user.role == "site" and user.branch and project.branch != user.branch:
        raise HTTPException(status_code=403, detail="他支店の工事は削除できません")
    if not crud.delete_project(db, project_id, user.username):
        raise HTTPException(status_code=404, detail="Project not found")
