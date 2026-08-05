from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from .. import crud, models

MONTH_END = {
    1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31,
}


def month_end_date(target_month: str) -> date:
    """Convert 'YYYY-MM' to the last day of that month."""
    year, month = (int(x) for x in target_month.split("-"))
    day = MONTH_END[month]
    if month == 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        day = 29
    return date(year, month, day)


def calculate_emissions(activity, factors) -> Optional[float]:
    """Pure helper (kept for unit tests): quantity x newest matching factor."""
    matching = [
        f for f in factors
        if f.category == activity.category
        and f.item_name == activity.item_name
        and f.unit == activity.unit
    ]
    if not matching:
        return None
    best = max(matching, key=lambda f: f.effective_from)
    return activity.quantity * best.factor_value


def calculate_all_for_month(
    db: Session, project_id: str, target_month: str
) -> dict:
    """
    Calculate emissions for all approved activity data for a project/month.
    Returns {"results": [...], "skipped": [...], "missing_factors": [...]}
    """
    activities = crud.list_activity_data(db, project_id=project_id, target_month=target_month, approved=True)
    results: list[models.EmissionResult] = []
    missing_factors: list[models.ActivityData] = []
    effective_on = month_end_date(target_month)
    for activity in activities:
        factor = crud.get_latest_factor(
            db,
            activity.category,
            activity.item_name,
            activity.unit,
            effective_on=effective_on,
            supplier=activity.supplier,
        )
        if factor is None:
            missing_factors.append(activity)
            continue
        co2_kg = activity.quantity * factor.factor_value
        result = crud.create_emission_result(db, activity, factor, co2_kg)
        results.append(result)
    return {
        "results": results,
        "missing_factors": missing_factors,
        "total_co2_kg": sum(r.co2_kg for r in results),
    }
