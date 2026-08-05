from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..security import require_at_least
from ..services import telematics

router = APIRouter(prefix="/api/telematics", tags=["telematics"])


@router.post("/import", response_model=schemas.TelematicsImportResult)
def import_telematics(
    body: schemas.TelematicsImportRequest,
    db: Session = Depends(get_db),
    user=Depends(require_at_least("site")),
):
    project = crud.get_project(db, body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if crud.is_month_closed(db, body.project_id, body.target_month):
        raise HTTPException(status_code=400, detail="対象月は締め済みです")
    try:
        rows = telematics.fetch_machine_data(
            project.name, body.target_month, supplier=user.branch
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    imported = 0
    skipped = 0
    items = []
    existing_keys = {
        (a.category, a.item_name, a.unit)
        for a in crud.list_activity_data(
            db, project_id=body.project_id, target_month=body.target_month
        )
    }
    for row in rows:
        key = ("machine", row["machine_name"], row["unit"])
        if key in existing_keys:
            skipped += 1
            continue
        try:
            crud.create_activity_data(
                db,
                schemas.ActivityDataCreate(
                    project_id=body.project_id,
                    target_month=body.target_month,
                    category="machine",
                    item_name=row["machine_name"],
                    quantity=row["hours"],
                    unit=row["unit"],
                    source_file="テレマティクス連携",
                    note=f"燃料消費 {row.get('fuel_l', 0)} L",
                    created_by=user.username,
                ),
                actor=user.username,
            )
            imported += 1
            items.append(row)
        except ValueError:
            skipped += 1
    return schemas.TelematicsImportResult(
        imported=imported,
        skipped=skipped,
        provider=telematics.get_mode(),
        items=items,
    )
