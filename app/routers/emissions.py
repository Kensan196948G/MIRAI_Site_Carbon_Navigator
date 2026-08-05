from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from .. import crud, schemas
from ..database import get_db
from ..services.calculator import calculate_all_for_month
from ..services.reduction import get_reduction_suggestions
from ..services.analysis import detect_anomalies, get_benchmark
from ..services.scope import scope_summary_from_results
from ..security import get_current_user

router = APIRouter(prefix="/api/emissions", tags=["emissions"])


@router.get("/dashboard")
def get_dashboard(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    projects = crud.list_projects(db)
    project_count = len(projects)
    results = crud.get_results_by_project(db)
    total_co2_kg = sum(r.co2_kg for r in results)
    by_category: dict[str, float] = {}
    for r in results:
        cat = r.activity.category
        by_category[cat] = by_category.get(cat, 0.0) + r.co2_kg
    missing = len(crud.find_missing_factors(db))
    trend = crud.get_monthly_trend(db)
    approved_count = len(
        [a for a in crud.list_activity_data(db) if a.approved]
    )
    return {
        "project_count": project_count,
        "total_co2_kg": total_co2_kg,
        "total_co2_t": total_co2_kg / 1000.0,
        "by_category": by_category,
        "missing_factor_count": missing,
        "approved_activity_count": approved_count,
        "trend": trend,
    }


@router.post("/calculate", response_model=list[schemas.CalculationResultItem])
def run_calculation(
    body: schemas.CalculateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    project = crud.get_project(db, body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    outcome = calculate_all_for_month(db, body.project_id, body.target_month)
    if outcome["missing_factors"]:
        crud.add_notification(
            db,
            message=f"排出係数未設定の活動量が {len(outcome['missing_factors'])} 件あります "
                    f"({project.name} / {body.target_month})",
            recipient_role="admin",
            link=f"/#/calculation?project={body.project_id}&month={body.target_month}",
        )
    items = []
    for result in outcome["results"]:
        activity = result.activity
        items.append(
            schemas.CalculationResultItem(
                result_id=result.result_id,
                activity_id=result.activity_id,
                factor_id=result.factor_id,
                co2_kg=result.co2_kg,
                calculated_at=result.calculated_at,
                factor_value=result.factor_value,
                factor_source=result.factor_source,
                factor_effective_from=result.factor_effective_from,
                item_name=result.item_name or activity.item_name,
                unit=result.unit or activity.unit,
                category=activity.category,
                quantity=activity.quantity,
            )
        )
    return items


@router.get("/results", response_model=list[schemas.EmissionResultRead])
def get_results(
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return crud.get_results_by_project(db, project_id=project_id, target_month=target_month)


@router.get("/summary", response_model=list[schemas.SummaryItem])
def get_summary(
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    results = crud.get_results_by_project(db, project_id=project_id, target_month=target_month)
    totals: dict[str, float] = {}
    for r in results:
        cat = r.activity.category
        totals[cat] = totals.get(cat, 0.0) + r.co2_kg
    return [schemas.SummaryItem(category=cat, total_co2_kg=total) for cat, total in sorted(totals.items())]


@router.get("/trend", response_model=list[schemas.TrendItem])
def get_trend(
    project_id: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return crud.get_monthly_trend(db, project_id=project_id, category=category)


@router.get("/missing-factors", response_model=list[schemas.MissingFactorItem])
def get_missing_factors(
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    activities = crud.find_missing_factors(db, project_id=project_id, target_month=target_month)
    return [
        schemas.MissingFactorItem(
            activity_id=a.activity_id,
            category=a.category,
            item_name=a.item_name,
            quantity=a.quantity,
            unit=a.unit,
        )
        for a in activities
    ]


@router.get("/benchmark", response_model=schemas.BenchmarkItem)
def get_benchmark_endpoint(
    project_id: str,
    target_month: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return get_benchmark(db, project, target_month)


@router.get("/anomalies", response_model=list[schemas.AnomalyItem])
def get_anomalies_endpoint(
    project_id: str,
    target_month: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not crud.get_project(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return detect_anomalies(db, project_id, target_month)


@router.get("/scope-summary", response_model=list[schemas.ScopeSummaryItem])
def get_scope_summary(
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    results = crud.get_results_by_project(db, project_id=project_id, target_month=target_month)
    if year:
        prefix = f"{year}-"
        results = [r for r in results if r.activity.target_month.startswith(prefix)]
    return scope_summary_from_results(
        [{"category": r.activity.category, "co2_kg": r.co2_kg} for r in results]
    )


@router.get("/reduction/{project_id}/{target_month}", response_model=list[schemas.ReductionSuggestion])
def get_reduction(
    project_id: str,
    target_month: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    results = crud.get_results_by_project(db, project_id=project_id, target_month=target_month)
    results_with_cat = [
        {"category": r.activity.category, "co2_kg": r.co2_kg}
        for r in results
    ]
    return get_reduction_suggestions(results_with_cat)
