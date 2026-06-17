from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from .. import crud, schemas
from ..database import get_db

router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.post("", response_model=schemas.ActivityDataRead, status_code=201)
def create_activity(activity: schemas.ActivityDataCreate, db: Session = Depends(get_db)):
    # Validate project exists
    project = crud.get_project(db, activity.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return crud.create_activity_data(db, activity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[schemas.ActivityDataRead])
def list_activities(
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return crud.list_activity_data(db, project_id=project_id, target_month=target_month)


@router.put("/{activity_id}/approve", response_model=schemas.ActivityDataRead)
def approve_activity(activity_id: str, body: schemas.ActivityDataApprove, db: Session = Depends(get_db)):
    activity = crud.approve_activity(db, activity_id, body.approved)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.post("/bulk", response_model=list[schemas.ActivityDataRead], status_code=201)
def bulk_create_activities(activities: list[schemas.ActivityDataCreate], db: Session = Depends(get_db)):
    results = []
    errors = []
    for i, activity in enumerate(activities):
        project = crud.get_project(db, activity.project_id)
        if not project:
            errors.append(f"Row {i}: Project {activity.project_id} not found")
            continue
        try:
            result = crud.create_activity_data(db, activity)
            results.append(result)
        except ValueError as e:
            errors.append(f"Row {i}: {str(e)}")
    if errors and not results:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    return results
