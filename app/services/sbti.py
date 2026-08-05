"""SBTi target progress calculation."""
from sqlalchemy.orm import Session

from .. import crud
from .scope import category_scope


def compute_sbti_progress(db: Session, targets=None) -> list[dict]:
    if targets is None:
        targets = crud.list_sbti_targets(db)
    results = crud.get_results_by_project(db)

    scope_totals: dict[str, float] = {"scope1": 0.0, "scope2": 0.0, "scope3": 0.0}
    for r in results:
        scope = category_scope(r.activity.category)
        scope_totals[scope] = scope_totals.get(scope, 0.0) + r.co2_kg

    items = []
    for t in targets:
        if not t.is_active:
            continue
        target_emissions_kg = t.base_emissions_kg * (1.0 - t.reduction_percent / 100.0)
        current = scope_totals.get(t.scope, 0.0)
        reduction_achieved_percent = 0.0
        if t.base_emissions_kg > 0:
            reduction_achieved_percent = (
                (t.base_emissions_kg - current) / t.base_emissions_kg * 100.0
            )
        progress_ratio = None
        if t.reduction_percent > 0:
            progress_ratio = reduction_achieved_percent / t.reduction_percent
        items.append({
            **{
                "target_id": t.target_id,
                "scope": t.scope,
                "name": t.name,
                "description": t.description,
                "base_year": t.base_year,
                "target_year": t.target_year,
                "base_emissions_kg": t.base_emissions_kg,
                "reduction_percent": t.reduction_percent,
                "is_active": t.is_active,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            },
            "target_emissions_kg": target_emissions_kg,
            "current_emissions_kg": current,
            "reduction_achieved_percent": reduction_achieved_percent,
            "progress_ratio": progress_ratio,
            "on_track": bool(progress_ratio is not None and progress_ratio >= 1.0),
        })
    return items
