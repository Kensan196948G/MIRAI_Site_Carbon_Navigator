from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from .. import crud
from ..database import get_db
from ..security import get_current_user
from ..services.reporter import (
    generate_monthly_report_csv,
    generate_monthly_report_excel,
    generate_monthly_report_pdf,
    generate_project_card_pdf,
)

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
