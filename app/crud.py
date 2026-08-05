from datetime import date, datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import and_
from sqlalchemy.orm import Session

from . import models, schemas
from .security import hash_password


def _new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def add_audit_log(
    db: Session,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    detail: Optional[str] = None,
) -> models.AuditLog:
    log = models.AuditLog(
        log_id=_new_id(),
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        created_at=utcnow(),
    )
    db.add(log)
    db.commit()
    return log


def list_audit_logs(db: Session, limit: int = 200) -> list[models.AuditLog]:
    return (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.created_at.desc())
        .limit(min(max(limit, 1), 1000))
        .all()
    )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def get_project(db: Session, project_id: str) -> Optional[models.Project]:
    return (
        db.query(models.Project)
        .filter(models.Project.project_id == project_id)
        .first()
    )


def create_project(db: Session, project: schemas.ProjectCreate, actor: str = "system"):
    db_project = models.Project(
        project_id=_new_id(),
        created_at=utcnow(),
        created_by=actor or project.created_by,
        **project.model_dump(exclude={"created_by"}),
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    add_audit_log(db, actor, "create", "project", db_project.project_id, db_project.name)
    return db_project


def list_projects(db: Session) -> list[models.Project]:
    return db.query(models.Project).order_by(models.Project.created_at.desc()).all()


def update_project(
    db: Session, project_id: str, updates: schemas.ProjectUpdate, actor: str
) -> Optional[models.Project]:
    project = get_project(db, project_id)
    if not project:
        return None
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    project.updated_at = utcnow()
    project.updated_by = actor
    db.commit()
    db.refresh(project)
    add_audit_log(db, actor, "update", "project", project_id)
    return project


def delete_project(db: Session, project_id: str, actor: str) -> bool:
    project = get_project(db, project_id)
    if not project:
        return False
    db.query(models.ReductionAction).filter(
        models.ReductionAction.project_id == project_id
    ).delete()
    db.query(models.ActivityData).filter(
        models.ActivityData.project_id == project_id
    ).delete()
    db.delete(project)
    db.commit()
    add_audit_log(db, actor, "delete", "project", project_id)
    return True


# ---------------------------------------------------------------------------
# Emission factors
# ---------------------------------------------------------------------------

def get_emission_factor(db: Session, factor_id: str) -> Optional[models.EmissionFactor]:
    return (
        db.query(models.EmissionFactor)
        .filter(models.EmissionFactor.factor_id == factor_id)
        .first()
    )


def create_emission_factor(
    db: Session, factor: schemas.EmissionFactorCreate, actor: str = "system"
):
    db_factor = models.EmissionFactor(
        factor_id=_new_id(),
        created_at=utcnow(),
        created_by=actor,
        **factor.model_dump(),
    )
    db.add(db_factor)
    db.commit()
    db.refresh(db_factor)
    add_audit_log(
        db,
        actor,
        "create",
        "factor",
        db_factor.factor_id,
        f"{db_factor.category}/{db_factor.item_name}",
    )
    return db_factor


def list_emission_factors(db: Session, category: Optional[str] = None):
    query = db.query(models.EmissionFactor)
    if category:
        query = query.filter(models.EmissionFactor.category == category)
    return query.order_by(
        models.EmissionFactor.category,
        models.EmissionFactor.item_name,
        models.EmissionFactor.effective_from.desc(),
    ).all()


def update_emission_factor(
    db: Session, factor_id: str, updates: schemas.EmissionFactorUpdate, actor: str
) -> Optional[models.EmissionFactor]:
    factor = get_emission_factor(db, factor_id)
    if not factor:
        return None
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(factor, key, value)
    factor.updated_at = utcnow()
    factor.updated_by = actor
    db.commit()
    db.refresh(factor)
    add_audit_log(db, actor, "update", "factor", factor_id)
    return factor


def delete_emission_factor(db: Session, factor_id: str, actor: str) -> bool:
    factor = get_emission_factor(db, factor_id)
    if not factor:
        return False
    db.delete(factor)
    db.commit()
    add_audit_log(db, actor, "delete", "factor", factor_id)
    return True


def get_latest_factor(
    db: Session,
    category: str,
    item_name: str,
    unit: str,
    effective_on: Optional[date] = None,
) -> Optional[models.EmissionFactor]:
    """Return the newest factor whose effective_from <= effective_on (or today)."""
    query = (
        db.query(models.EmissionFactor)
        .filter(
            models.EmissionFactor.category == category,
            models.EmissionFactor.item_name == item_name,
            models.EmissionFactor.unit == unit,
        )
    )
    if effective_on is not None:
        query = query.filter(models.EmissionFactor.effective_from <= effective_on)
    return query.order_by(models.EmissionFactor.effective_from.desc()).first()


def list_factor_versions(
    db: Session, category: str, item_name: str, unit: str
) -> list[models.EmissionFactor]:
    return (
        db.query(models.EmissionFactor)
        .filter(
            models.EmissionFactor.category == category,
            models.EmissionFactor.item_name == item_name,
            models.EmissionFactor.unit == unit,
        )
        .order_by(models.EmissionFactor.effective_from.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

def create_activity_data(
    db: Session, activity: schemas.ActivityDataCreate, actor: str = "system"
):
    # Check for duplicate (unit included)
    existing = db.query(models.ActivityData).filter(
        and_(
            models.ActivityData.project_id == activity.project_id,
            models.ActivityData.target_month == activity.target_month,
            models.ActivityData.category == activity.category,
            models.ActivityData.item_name == activity.item_name,
            models.ActivityData.unit == activity.unit,
        )
    ).first()
    if existing:
        raise ValueError(
            "Duplicate activity data for same project/month/category/item_name/unit"
        )

    db_activity = models.ActivityData(
        activity_id=_new_id(),
        created_at=utcnow(),
        approved=False,
        created_by=actor or activity.created_by,
        **activity.model_dump(exclude={"created_by"}),
    )
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)
    add_audit_log(
        db,
        actor,
        "create",
        "activity",
        db_activity.activity_id,
        f"{db_activity.category}/{db_activity.item_name} {db_activity.quantity}{db_activity.unit}",
    )
    project = get_project(db, activity.project_id)
    add_notification(
        db,
        message=f"活動量が登録されました: {project.name if project else activity.project_id} / "
                f"{db_activity.item_name} {db_activity.quantity:,.3f}{db_activity.unit}",
        recipient_role="reviewer",
        link=f"/#/activities?project={activity.project_id}&month={activity.target_month}",
    )
    return db_activity


def list_activity_data(
    db: Session,
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    approved: Optional[bool] = None,
):
    query = db.query(models.ActivityData)
    if project_id:
        query = query.filter(models.ActivityData.project_id == project_id)
    if target_month:
        query = query.filter(models.ActivityData.target_month == target_month)
    if approved is not None:
        query = query.filter(models.ActivityData.approved == approved)
    return query.order_by(models.ActivityData.created_at.desc()).all()


def get_activity(db: Session, activity_id: str) -> Optional[models.ActivityData]:
    return (
        db.query(models.ActivityData)
        .filter(models.ActivityData.activity_id == activity_id)
        .first()
    )


def update_activity(
    db: Session,
    activity_id: str,
    updates: schemas.ActivityDataUpdate,
    actor: str,
) -> Optional[models.ActivityData]:
    activity = get_activity(db, activity_id)
    if not activity:
        return None
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(activity, key, value)
    activity.updated_at = utcnow()
    activity.updated_by = actor
    # Data changed -> reset approval state so reviewers re-check
    activity.approved = False
    activity.approved_by = None
    activity.approved_at = None
    db.commit()
    db.refresh(activity)
    add_audit_log(db, actor, "update", "activity", activity_id)
    project = get_project(db, activity.project_id)
    add_notification(
        db,
        message=f"活動量が更新され承認解除されました: {project.name if project else activity.project_id} / "
                f"{activity.item_name}",
        recipient_role="reviewer",
        link=f"/#/activities?project={activity.project_id}&month={activity.target_month}",
    )
    return activity


def delete_activity(db: Session, activity_id: str, actor: str) -> bool:
    activity = get_activity(db, activity_id)
    if not activity:
        return False
    db.query(models.EmissionResult).filter(
        models.EmissionResult.activity_id == activity_id
    ).delete()
    db.delete(activity)
    db.commit()
    add_audit_log(db, actor, "delete", "activity", activity_id)
    add_notification(
        db,
        message=f"活動量が削除されました: {activity.item_name} ({activity.project_id} / {activity.target_month})",
        recipient_role="reviewer",
    )
    return True


def approve_activity(
    db: Session, activity_id: str, approved: bool, actor: str
) -> Optional[models.ActivityData]:
    activity = get_activity(db, activity_id)
    if not activity:
        return None
    activity.approved = approved
    activity.approved_by = actor if approved else None
    activity.approved_at = utcnow() if approved else None
    activity.updated_at = utcnow()
    activity.updated_by = actor
    db.commit()
    db.refresh(activity)
    add_audit_log(
        db, actor, "approve" if approved else "unapprove", "activity", activity_id
    )
    project = get_project(db, activity.project_id)
    add_notification(
        db,
        message=f"活動量が{'承認' if approved else '承認取消'}されました: "
                f"{project.name if project else activity.project_id} / {activity.item_name}",
        recipient_role="site",
    )
    return activity


# ---------------------------------------------------------------------------
# Emission results
# ---------------------------------------------------------------------------

def create_emission_result(
    db: Session,
    activity: models.ActivityData,
    factor: models.EmissionFactor,
    co2_kg: float,
):
    existing = (
        db.query(models.EmissionResult)
        .filter(models.EmissionResult.activity_id == activity.activity_id)
        .first()
    )
    snapshot = {
        "factor_id": factor.factor_id,
        "co2_kg": co2_kg,
        "calculated_at": utcnow(),
        "factor_value": factor.factor_value,
        "factor_source": factor.source,
        "factor_effective_from": factor.effective_from,
        "item_name": activity.item_name,
        "unit": activity.unit,
    }
    if existing:
        for key, value in snapshot.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing

    db_result = models.EmissionResult(
        result_id=_new_id(),
        activity_id=activity.activity_id,
        **snapshot,
    )
    db.add(db_result)
    db.commit()
    db.refresh(db_result)
    return db_result


def get_results_by_project(
    db: Session,
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
):
    query = db.query(models.EmissionResult).join(
        models.ActivityData,
        models.EmissionResult.activity_id == models.ActivityData.activity_id,
    )
    if project_id:
        query = query.filter(models.ActivityData.project_id == project_id)
    if target_month:
        query = query.filter(models.ActivityData.target_month == target_month)
    return query.order_by(models.ActivityData.category, models.ActivityData.item_name).all()


def get_monthly_trend(
    db: Session, project_id: Optional[str] = None, category: Optional[str] = None
) -> list[dict]:
    query = db.query(models.EmissionResult, models.ActivityData).join(
        models.ActivityData,
        models.EmissionResult.activity_id == models.ActivityData.activity_id,
    )
    if project_id:
        query = query.filter(models.ActivityData.project_id == project_id)
    if category:
        query = query.filter(models.ActivityData.category == category)
    rows = query.all()
    totals: dict[str, dict] = {}
    for result, activity in rows:
        month = activity.target_month
        entry = totals.setdefault(
            month, {"target_month": month, "by_category": {}, "total_co2_kg": 0.0}
        )
        cat = activity.category
        entry["by_category"][cat] = entry["by_category"].get(cat, 0.0) + result.co2_kg
    # aggregate total per month
    result = []
    for month in sorted(totals.keys()):
        entry = totals[month]
        entry["total_co2_kg"] = sum(entry["by_category"].values())
        entry["total_co2_t"] = entry["total_co2_kg"] / 1000.0
        result.append(entry)
    return result


def find_missing_factors(
    db: Session, project_id: Optional[str] = None, target_month: Optional[str] = None
) -> list[models.ActivityData]:
    query = db.query(models.ActivityData).filter(models.ActivityData.approved == True)  # noqa: E712
    if project_id:
        query = query.filter(models.ActivityData.project_id == project_id)
    if target_month:
        query = query.filter(models.ActivityData.target_month == target_month)
    missing = []
    for activity in query.all():
        factor = get_latest_factor(
            db, activity.category, activity.item_name, activity.unit
        )
        if factor is None:
            missing.append(activity)
    return missing


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def get_user(db: Session, user_id: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.user_id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    return (
        db.query(models.User)
        .filter(models.User.username == username.lower())
        .first()
    )


def create_user(db: Session, user: schemas.UserCreate, actor: str = "system"):
    if get_user_by_username(db, user.username):
        raise ValueError("Username already exists")
    db_user = models.User(
        user_id=_new_id(),
        username=user.username.lower(),
        display_name=user.display_name or user.username,
        password_hash=hash_password(user.password),
        role=user.role,
        is_active=True,
        created_at=utcnow(),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    add_audit_log(db, actor, "create", "user", db_user.user_id, db_user.username)
    return db_user


def list_users(db: Session) -> list[models.User]:
    return db.query(models.User).order_by(models.User.created_at).all()


def set_user_active(db: Session, user_id: str, is_active: bool, actor: str):
    user = get_user(db, user_id)
    if not user:
        return None
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    add_audit_log(db, actor, "update", "user", user_id, f"is_active={is_active}")
    return user


def update_user(
    db: Session, user_id: str, updates: schemas.UserUpdate, actor: str
) -> Optional[models.User]:
    user = get_user(db, user_id)
    if not user:
        return None
    data = updates.model_dump(exclude_unset=True)
    if "password" in data and data["password"]:
        user.password_hash = hash_password(data.pop("password"))
    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)
    db.commit()
    db.refresh(user)
    add_audit_log(db, actor, "update", "user", user_id, f"username={user.username}")
    return user


# ---------------------------------------------------------------------------
# Reduction actions
# ---------------------------------------------------------------------------

def create_reduction_action(
    db: Session, action: schemas.ReductionActionCreate, actor: str
):
    db_action = models.ReductionAction(
        action_id=_new_id(),
        created_at=utcnow(),
        created_by=actor,
        **action.model_dump(),
    )
    db.add(db_action)
    db.commit()
    db.refresh(db_action)
    add_audit_log(db, actor, "create", "reduction_action", db_action.action_id)
    project = get_project(db, action.project_id)
    add_notification(
        db,
        message=f"削減アクションが登録されました: {project.name if project else action.project_id} / {action.suggestion}",
        recipient_role="reviewer",
    )
    return db_action


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def add_notification(
    db: Session,
    message: str,
    recipient_role: Optional[str] = None,
    recipient_username: Optional[str] = None,
    link: Optional[str] = None,
) -> models.Notification:
    notification = models.Notification(
        notification_id=_new_id(),
        recipient_role=recipient_role,
        recipient_username=recipient_username,
        message=message,
        link=link,
        is_read=False,
        created_at=utcnow(),
    )
    db.add(notification)
    db.commit()
    return notification


def list_notifications(
    db: Session, user: models.User, unread_only: bool = False, limit: int = 100
) -> list[models.Notification]:
    query = db.query(models.Notification).filter(
        (
            (models.Notification.recipient_role == user.role)
            | (models.Notification.recipient_username == user.username)
            | (
                models.Notification.recipient_role.is_(None)
                & models.Notification.recipient_username.is_(None)
            )
        )
    )
    if unread_only:
        query = query.filter(models.Notification.is_read == False)  # noqa: E712
    return query.order_by(models.Notification.created_at.desc()).limit(limit).all()


def unread_notification_count(db: Session, user: models.User) -> int:
    return len(list_notifications(db, user, unread_only=True, limit=1000))


def mark_notification_read(
    db: Session, notification_id: str, user: models.User
) -> bool:
    notification = (
        db.query(models.Notification)
        .filter(models.Notification.notification_id == notification_id)
        .first()
    )
    if not notification:
        return False
    owned = (
        notification.recipient_username == user.username
        or notification.recipient_role == user.role
        or (notification.recipient_role is None and notification.recipient_username is None)
    )
    if not owned:
        return False
    notification.is_read = True
    db.commit()
    return True


def mark_all_notifications_read(db: Session, user: models.User) -> int:
    notifications = list_notifications(db, user, unread_only=True, limit=1000)
    count = 0
    for n in notifications:
        n.is_read = True
        count += 1
    db.commit()
    return count


def list_reduction_actions(
    db: Session,
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    status: Optional[str] = None,
):
    query = db.query(models.ReductionAction)
    if project_id:
        query = query.filter(models.ReductionAction.project_id == project_id)
    if target_month:
        query = query.filter(models.ReductionAction.target_month == target_month)
    if status:
        query = query.filter(models.ReductionAction.status == status)
    return query.order_by(models.ReductionAction.created_at.desc()).all()


def get_reduction_action(db: Session, action_id: str):
    return (
        db.query(models.ReductionAction)
        .filter(models.ReductionAction.action_id == action_id)
        .first()
    )


def update_reduction_action(
    db: Session,
    action_id: str,
    updates: schemas.ReductionActionUpdate,
    actor: str,
):
    action = get_reduction_action(db, action_id)
    if not action:
        return None
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(action, key, value)
    action.updated_at = utcnow()
    action.updated_by = actor
    db.commit()
    db.refresh(action)
    add_audit_log(db, actor, "update", "reduction_action", action_id)
    return action


def delete_reduction_action(db: Session, action_id: str, actor: str) -> bool:
    action = get_reduction_action(db, action_id)
    if not action:
        return False
    db.delete(action)
    db.commit()
    add_audit_log(db, actor, "delete", "reduction_action", action_id)
    return True
