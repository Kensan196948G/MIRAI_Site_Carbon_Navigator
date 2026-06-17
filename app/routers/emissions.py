from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from .. import crud, schemas
from ..database import get_db
from ..services.calculator import calculate_all_for_month
from ..services.reduction import get_reduction_suggestions

router = APIRouter(prefix="/api/emissions", tags=["emissions"])


@router.post("/calculate", response_model=list[schemas.EmissionResultRead])
def run_calculation(body: schemas.CalculateRequest, db: Session = Depends(get_db)):
    project = crud.get_project(db, body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    results = calculate_all_for_month(db, body.project_id, body.target_month)
    return results


@router.get("/results", response_model=list[schemas.EmissionResultRead])
def get_results(
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return crud.get_results_by_project(db, project_id=project_id, target_month=target_month)


@router.get("/summary", response_model=list[schemas.SummaryItem])
def get_summary(
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    db: Session = Depends(get_db),
):
    results = crud.get_results_by_project(db, project_id=project_id, target_month=target_month)
    totals: dict[str, float] = {}
    for r in results:
        cat = r.activity.category
        totals[cat] = totals.get(cat, 0.0) + r.co2_kg
    return [schemas.SummaryItem(category=cat, total_co2_kg=total) for cat, total in sorted(totals.items())]


@router.get("/reduction/{project_id}/{target_month}", response_model=list[schemas.ReductionSuggestion])
def get_reduction(project_id: str, target_month: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    results = crud.get_results_by_project(db, project_id=project_id, target_month=target_month)
    results_with_cat = [
        {"category": r.activity.category, "co2_kg": r.co2_kg}
        for r in results
    ]
    return get_reduction_suggestions(results_with_cat)
