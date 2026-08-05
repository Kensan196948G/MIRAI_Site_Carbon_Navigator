from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from .. import crud, schemas
from ..database import get_db
from ..services.calculator import calculate_all_for_month
from ..services.reduction import get_reduction_suggestions
from ..services.analysis import (
    detect_anomalies,
    forecast_next_month,
    get_benchmark,
    get_comparison,
    get_missing_months,
    simulate_scenario,
)
from ..services.scope import scope_summary_from_results
from ..security import get_current_user

router = APIRouter(prefix="/api/emissions", tags=["emissions"])


def _ensure_project_access(user, db: Session, project_id: Optional[str]):
    if project_id and not crud.has_project_access(db, user, project_id):
        raise HTTPException(status_code=403, detail="Project access denied")


@router.get("/dashboard")
def get_dashboard(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    projects = crud.list_projects_for_user(db, user)
    allowed_ids = {p.project_id for p in projects}
    project_count = len(projects)
    results = [
        r for r in crud.get_results_by_project(db)
        if r.activity.project_id in allowed_ids
    ]
    total_co2_kg = sum(r.co2_kg for r in results)
    by_category: dict[str, float] = {}
    for r in results:
        cat = r.activity.category
        by_category[cat] = by_category.get(cat, 0.0) + r.co2_kg
    missing_activities = [
        a for a in crud.find_missing_factors(db)
        if a.project_id in allowed_ids
    ]
    missing = len(missing_activities)
    monthly: dict[str, dict] = {}
    for r in results:
        month = r.activity.target_month
        entry = monthly.setdefault(
            month, {"target_month": month, "by_category": {}, "total_co2_kg": 0.0}
        )
        cat = r.activity.category
        entry["by_category"][cat] = entry["by_category"].get(cat, 0.0) + r.co2_kg
        entry["total_co2_kg"] += r.co2_kg
    trend = []
    for month in sorted(monthly.keys()):
        entry = monthly[month]
        entry["total_co2_t"] = entry["total_co2_kg"] / 1000.0
        trend.append(entry)
    approved_count = len(
        [a for a in crud.list_activity_data(db) if a.approved and a.project_id in allowed_ids]
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
    if crud.is_month_closed(db, body.project_id, body.target_month):
        raise HTTPException(status_code=400, detail="対象月は締め済みのため再算定できません")
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
    _ensure_project_access(user, db, project_id)
    return crud.get_results_by_project(db, project_id=project_id, target_month=target_month)


@router.get("/summary", response_model=list[schemas.SummaryItem])
def get_summary(
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ensure_project_access(user, db, project_id)
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
    _ensure_project_access(user, db, project_id)
    return crud.get_monthly_trend(db, project_id=project_id, category=category)


@router.get("/missing-factors", response_model=list[schemas.MissingFactorItem])
def get_missing_factors(
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ensure_project_access(user, db, project_id)
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
    _ensure_project_access(user, db, project_id)
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
    _ensure_project_access(user, db, project_id)
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
    _ensure_project_access(user, db, project_id)
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
    _ensure_project_access(user, db, project_id)
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    results = crud.get_results_by_project(db, project_id=project_id, target_month=target_month)
    results_with_cat = [
        {"category": r.activity.category, "co2_kg": r.co2_kg}
        for r in results
    ]
    return get_reduction_suggestions(results_with_cat)


@router.get("/reminders", response_model=list[schemas.ReminderItem])
def get_reminders(
    target_month: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return crud.get_monthly_reminders(db, target_month)


@router.get("/comparison", response_model=schemas.ComparisonItem)
def get_comparison_endpoint(
    project_id: str,
    target_month: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ensure_project_access(user, db, project_id)
    return get_comparison(db, project_id, target_month)


@router.get("/missing-months", response_model=list[schemas.MissingMonthItem])
def get_missing_months_endpoint(
    project_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ensure_project_access(user, db, project_id)
    return get_missing_months(db, project_id)


@router.get("/forecast", response_model=schemas.ForecastItem)
def get_forecast_endpoint(
    project_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ensure_project_access(user, db, project_id)
    return forecast_next_month(db, project_id)


@router.post("/scenario-simulate", response_model=schemas.ScenarioResult)
def simulate_scenario_endpoint(
    body: schemas.ScenarioRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _ensure_project_access(user, db, body.project_id)
    if not crud.get_project(db, body.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return simulate_scenario(
        db,
        body.project_id,
        body.target_month,
        body.adjustments.model_dump(),
    )


@router.get("/month-status", response_model=list[schemas.MonthStatusItem])
def get_month_status_endpoint(
    target_month: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    statuses = crud.get_month_status(db, target_month)
    if user.role == "client":
        allowed = set(crud.accessible_project_ids(db, user))
        statuses = [s for s in statuses if s["project_id"] in allowed]
    elif user.role == "site" and user.branch:
        statuses = [s for s in statuses if s["branch"] == user.branch]
    return statuses
