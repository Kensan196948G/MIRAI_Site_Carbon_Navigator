from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from .. import crud
from ..database import get_db
from ..services.reporter import generate_monthly_report_excel

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/monthly/{project_id}/{target_month}")
def download_monthly_report(project_id: str, target_month: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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

    xlsx_bytes = generate_monthly_report_excel(project, target_month, results_summary)

    filename = f"co2_report_{project_id}_{target_month}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
