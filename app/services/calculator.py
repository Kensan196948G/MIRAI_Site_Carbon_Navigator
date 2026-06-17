from sqlalchemy.orm import Session
from .. import models, crud
from typing import Optional


def calculate_emissions(activity: models.ActivityData, factors: list[models.EmissionFactor]) -> Optional[float]:
    """Find matching factor and return CO2 kg = quantity * factor_value"""
    matching = [
        f for f in factors
        if f.category == activity.category
        and f.item_name == activity.item_name
        and f.unit == activity.unit
    ]
    if not matching:
        return None
    # Use the factor with the latest effective_from
    best = max(matching, key=lambda f: f.effective_from)
    return activity.quantity * best.factor_value


def calculate_all_for_month(db: Session, project_id: str, target_month: str) -> list[models.EmissionResult]:
    """Calculate emissions for all approved activity data for a project/month."""
    activities = crud.list_activity_data(db, project_id=project_id, target_month=target_month, approved=True)
    results = []
    for activity in activities:
        factor = crud.get_latest_factor(db, activity.category, activity.item_name, activity.unit)
        if factor is None:
            continue
        co2_kg = activity.quantity * factor.factor_value
        result = crud.create_emission_result(db, activity.activity_id, factor.factor_id, co2_kg)
        results.append(result)
    return results
