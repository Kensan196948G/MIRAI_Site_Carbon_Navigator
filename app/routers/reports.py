from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..security import get_current_user
from ..services.reporter import (
    generate_annual_report_pdf,
    generate_monthly_report_csv,
    generate_monthly_report_excel,
    generate_monthly_report_pdf,
    generate_project_card_pdf,
)
from ..services.sbti import compute_sbti_progress
from ..services.scope import scope_summary_from_results

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/monthly/{project_id}/{target_month}")
def download_monthly_report(
    project_id: str,
    target_month: str,
    format: str = "xlsx",
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not crud.has_project_access(db, user, project_id):
        raise HTTPException(status_code=403, detail="Project access denied")

    results = crud.get_results_by_project(db, project_id=project_id, target_month=target_month)

    results_summary = []
    for r in results:
        activity = r.activity
        factor = r.factor
        results_summary.append({
            "category": activity.category,
            "item_name": activity.item_name,
            "quantity": activity.quantity,
            "unit": activity.unit,
            "factor_value": factor.factor_value if factor else 0.0,
            "co2_kg": r.co2_kg,
        })

    if format == "csv":
        content = generate_monthly_report_csv(project, target_month, results_summary)
        media_type = "text/csv; charset=utf-8"
        filename = f"co2_report_{project_id}_{target_month}.csv"
    elif format == "pdf":
        content = generate_monthly_report_pdf(project, target_month, results_summary)
        media_type = "application/pdf"
        filename = f"co2_report_{project_id}_{target_month}.pdf"
    else:
        content = generate_monthly_report_excel(project, target_month, results_summary)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"co2_report_{project_id}_{target_month}.xlsx"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/card/{project_id}")
def download_project_card(
    project_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not crud.has_project_access(db, user, project_id):
        raise HTTPException(status_code=403, detail="Project access denied")

    results = crud.get_results_by_project(db, project_id=project_id)
    category_totals: dict[str, float] = {}
    for r in results:
        cat = r.activity.category
        category_totals[cat] = category_totals.get(cat, 0.0) + r.co2_kg

    trend_rows = [
        t for t in crud.get_monthly_trend(db, project_id=project_id)
    ]
    actions = [
        {
            "target_month": a.target_month,
            "category": a.category,
            "suggestion": a.suggestion,
            "status": a.status,
            "estimated_reduction_kg": a.estimated_reduction_kg,
            "actual_reduction_kg": a.actual_reduction_kg,
        }
        for a in crud.list_reduction_actions(db, project_id=project_id)
    ]
    feedbacks = [
        {"target_month": f.target_month, "content": f.content}
        for f in crud.list_site_feedbacks(db, project_id=project_id)
    ]
    content = generate_project_card_pdf(
        project, trend_rows, category_totals, actions, feedbacks
    )
    filename = f"project_card_{project_id}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/annual/{year}")
def download_annual_report(
    year: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    projects = crud.list_projects_for_user(db, user)
    allowed_ids = {p.project_id for p in projects}
    prefix = f"{year}-"
    projects_summary = []
    all_results = []
    for project in projects:
        results = [
            r for r in crud.get_results_by_project(db, project_id=project.project_id)
            if r.activity.target_month.startswith(prefix)
        ]
        all_results.extend(results)
        projects_summary.append({
            "name": project.name,
            "branch": project.branch,
            "work_type": project.work_type,
            "total_co2_kg": sum(r.co2_kg for r in results),
        })
    scope_items = scope_summary_from_results(
        [{"category": r.activity.category, "co2_kg": r.co2_kg} for r in all_results]
    )
    scope_totals = {item["scope"]: item["total_co2_kg"] for item in scope_items}
    sbti_progress = [
        item for item in compute_sbti_progress(db)
        if item["current_emissions_kg"] > 0 or item["base_emissions_kg"] > 0
    ]
    actions = [
        a for a in crud.list_reduction_actions(db)
        if a.project_id in allowed_ids
    ]
    implemented = [a for a in actions if a.status == "implemented"]
    actions_summary = {
        "implemented": len(implemented),
        "total_reduction_kg": sum(a.actual_reduction_kg or 0.0 for a in implemented),
    }
    credits_summary = crud.offset_summary(db)
    content = generate_annual_report_pdf(
        year,
        projects_summary,
        scope_totals,
        sbti_progress,
        actions_summary,
        credits_summary,
    )
    filename = f"annual_report_{year}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
