from sqlalchemy.orm import Session
from sqlalchemy import and_
from . import models, schemas
import uuid
from datetime import datetime, timezone


def get_project(db: Session, project_id: str):
    return db.query(models.Project).filter(models.Project.project_id == project_id).first()


def create_project(db: Session, project: schemas.ProjectCreate):
    db_project = models.Project(
        project_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        **project.model_dump()
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


def list_projects(db: Session):
    return db.query(models.Project).all()


def get_emission_factor(db: Session, factor_id: str):
    return db.query(models.EmissionFactor).filter(models.EmissionFactor.factor_id == factor_id).first()


def create_emission_factor(db: Session, factor: schemas.EmissionFactorCreate):
    db_factor = models.EmissionFactor(
        factor_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        **factor.model_dump()
    )
    db.add(db_factor)
    db.commit()
    db.refresh(db_factor)
    return db_factor


def list_emission_factors(db: Session, category: str = None):
    query = db.query(models.EmissionFactor)
    if category:
        query = query.filter(models.EmissionFactor.category == category)
    return query.all()


def get_latest_factor(db: Session, category: str, item_name: str, unit: str):
    return (
        db.query(models.EmissionFactor)
        .filter(
            models.EmissionFactor.category == category,
            models.EmissionFactor.item_name == item_name,
            models.EmissionFactor.unit == unit,
        )
        .order_by(models.EmissionFactor.effective_from.desc())
        .first()
    )


def create_activity_data(db: Session, activity: schemas.ActivityDataCreate):
    # Check for duplicate
    existing = db.query(models.ActivityData).filter(
        and_(
            models.ActivityData.project_id == activity.project_id,
            models.ActivityData.target_month == activity.target_month,
            models.ActivityData.category == activity.category,
            models.ActivityData.item_name == activity.item_name,
        )
    ).first()
    if existing:
        raise ValueError("Duplicate activity data for same project/month/category/item_name")

    db_activity = models.ActivityData(
        activity_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        approved=False,
        **activity.model_dump()
    )
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)
    return db_activity


def list_activity_data(db: Session, project_id: str = None, target_month: str = None, approved: bool = None):
    query = db.query(models.ActivityData)
    if project_id:
        query = query.filter(models.ActivityData.project_id == project_id)
    if target_month:
        query = query.filter(models.ActivityData.target_month == target_month)
    if approved is not None:
        query = query.filter(models.ActivityData.approved == approved)
    return query.all()


def approve_activity(db: Session, activity_id: str, approved: bool):
    activity = db.query(models.ActivityData).filter(models.ActivityData.activity_id == activity_id).first()
    if not activity:
        return None
    activity.approved = approved
    db.commit()
    db.refresh(activity)
    return activity


def create_emission_result(db: Session, activity_id: str, factor_id: str, co2_kg: float):
    # Check if result already exists for this activity
    existing = db.query(models.EmissionResult).filter(
        models.EmissionResult.activity_id == activity_id
    ).first()
    if existing:
        existing.factor_id = factor_id
        existing.co2_kg = co2_kg
        existing.calculated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    db_result = models.EmissionResult(
        result_id=str(uuid.uuid4()),
        activity_id=activity_id,
        factor_id=factor_id,
        co2_kg=co2_kg,
        calculated_at=datetime.now(timezone.utc),
    )
    db.add(db_result)
    db.commit()
    db.refresh(db_result)
    return db_result


def get_results_by_project(db: Session, project_id: str = None, target_month: str = None):
    query = (
        db.query(models.EmissionResult)
        .join(models.ActivityData, models.EmissionResult.activity_id == models.ActivityData.activity_id)
    )
    if project_id:
        query = query.filter(models.ActivityData.project_id == project_id)
    if target_month:
        query = query.filter(models.ActivityData.target_month == target_month)
    return query.all()
