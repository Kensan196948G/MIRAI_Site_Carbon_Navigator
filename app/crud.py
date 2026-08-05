from datetime import date, datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import and_
from sqlalchemy.orm import Session

from . import models, schemas
from .security import hash_password
from .services.notify import deliver_external
from .services.units import convert as convert_unit


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
    db.query(models.SiteFeedback).filter(
        models.SiteFeedback.project_id == project_id
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
    supplier: Optional[str] = None,
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
    if supplier:
        supplier_match = (
            query.filter(models.EmissionFactor.supplier == supplier)
            .order_by(models.EmissionFactor.effective_from.desc())
            .first()
        )
        if supplier_match:
            return supplier_match
        return (
            query.filter(models.EmissionFactor.supplier.is_(None))
            .order_by(models.EmissionFactor.effective_from.desc())
            .first()
        )
    return (
        query.filter(models.EmissionFactor.supplier.is_(None))
        .order_by(models.EmissionFactor.effective_from.desc())
        .first()
    )


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
    # Normalize unit automatically when the entered unit is convertible to a
    # factor unit (e.g. kL -> L). This keeps calculations and reports consistent.
    if not get_latest_factor(
        db,
        activity.category,
        activity.item_name,
        activity.unit,
        supplier=activity.supplier,
    ):
        for candidate in list_emission_factors(db, category=activity.category):
            if candidate.item_name != activity.item_name:
                continue
            if activity.supplier and candidate.supplier != activity.supplier:
                continue
            try:
                converted = convert_unit(activity.quantity, activity.unit, candidate.unit)
                old_note = activity.note or ""
                note = (
                    f"{old_note}；自動換算: {activity.quantity:g}{activity.unit}"
                    f" → {converted['converted_value']:g}{candidate.unit}"
                ).strip("；")
                activity.quantity = converted["converted_value"]
                activity.unit = candidate.unit
                activity.note = note
                break
            except ValueError:
                continue

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
    data = updates.model_dump(exclude_unset=True)
    old_values = {key: getattr(activity, key) for key in data}
    for key, value in data.items():
        setattr(activity, key, value)
    # CO2 impact of the change (uses the latest applicable factor)
    co2_before = None
    co2_after = None
    factor = get_latest_factor(
        db, activity.category, activity.item_name, activity.unit,
        supplier=activity.supplier,
    )
    if factor:
        co2_after = activity.quantity * factor.factor_value
        # recompute before with old quantity
        old_quantity = old_values.get("quantity", activity.quantity)
        co2_before = old_quantity * factor.factor_value
    for key in data:
        old_value = old_values.get(key)
        if old_value == getattr(activity, key):
            continue
        log_change(
            db,
            activity_id=activity_id,
            actor=actor,
            field=key,
            old_value=old_value,
            new_value=getattr(activity, key),
            co2_kg_before=co2_before,
            co2_kg_after=co2_after,
        )
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


def log_change(
    db: Session,
    activity_id: str,
    actor: str,
    field: str,
    old_value,
    new_value,
    co2_kg_before: Optional[float] = None,
    co2_kg_after: Optional[float] = None,
) -> models.ActivityChangeLog:
    def _fmt(value):
        if value is None:
            return None
        if isinstance(value, float):
            return f"{value:.6g}"
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    change = models.ActivityChangeLog(
        change_id=_new_id(),
        activity_id=activity_id,
        actor=actor,
        field=field,
        old_value=_fmt(old_value),
        new_value=_fmt(new_value),
        co2_kg_before=co2_kg_before,
        co2_kg_after=co2_kg_after,
        created_at=utcnow(),
    )
    db.add(change)
    db.commit()
    return change


def list_activity_changes(db: Session, activity_id: str) -> list[models.ActivityChangeLog]:
    return (
        db.query(models.ActivityChangeLog)
        .filter(models.ActivityChangeLog.activity_id == activity_id)
        .order_by(models.ActivityChangeLog.created_at.desc())
        .all()
    )


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


def transition_approval(
    db: Session,
    activity_id: str,
    action: str,
    actor: str,
    comment: Optional[str] = None,
) -> Optional[models.ActivityData]:
    """Multi-stage approval: draft -> site_submitted -> branch_approved -> env_approved."""
    activity = get_activity(db, activity_id)
    if not activity:
        return None
    current = activity.approval_status or "draft"
    allowed = {
        "submit": {"draft"},
        "withdraw": {"site_submitted"},
        "approve_branch": {"site_submitted"},
        "reject": {"site_submitted", "branch_approved"},
        "approve_env": {"branch_approved", "site_submitted"},
    }
    if action not in allowed:
        raise ValueError("Invalid approval action")
    if current not in allowed[action]:
        raise ValueError(
            f"Approval action '{action}' not allowed from status '{current}'"
        )
    if action == "submit":
        activity.approval_status = "site_submitted"
        activity.approved = False
    elif action == "withdraw":
        activity.approval_status = "draft"
        activity.approved = False
    elif action == "approve_branch":
        activity.approval_status = "branch_approved"
        activity.approved = False
    elif action == "approve_env":
        activity.approval_status = "env_approved"
        activity.approved = True
        activity.approved_by = actor
        activity.approved_at = utcnow()
    elif action == "reject":
        activity.approval_status = "draft"
        activity.approved = False
        activity.approved_by = None
        activity.approved_at = None
    activity.updated_at = utcnow()
    activity.updated_by = actor
    if comment:
        add_activity_comment(db, activity_id, f"[承認:{action}] {comment}", actor)
    db.commit()
    db.refresh(activity)
    add_audit_log(db, actor, "approve", "activity", activity_id, f"{action} ({current})")
    add_notification(
        db,
        message=f"承認ステータスが変更されました: {activity.item_name} → {activity.approval_status}",
        recipient_role="reviewer" if action in ("submit",) else "site",
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


def set_user_totp(db: Session, user_id: str, secret: str) -> models.User:
    user = get_user(db, user_id)
    if not user:
        raise ValueError("User not found")
    user.totp_secret = secret
    user.is_2fa_enabled = True
    db.commit()
    db.refresh(user)
    return user


def find_or_create_oidc_user(
    db: Session, sub: str, email: Optional[str], display_name: Optional[str]
) -> models.User:
    user = db.query(models.User).filter(models.User.oidc_sub == sub).first()
    if user:
        return user
    if email:
        user = get_user_by_username(db, email.split("@")[0])
    if not user:
        username = (email or f"oidc_{sub}").split("@")[0][:50]
        base = username
        counter = 1
        while get_user_by_username(db, username):
            username = f"{base}_{counter}"
            counter += 1
        user = models.User(
            user_id=_new_id(),
            username=username,
            display_name=display_name or username,
            password_hash="!oidc",  # no password login for OIDC users
            role="viewer",
            email=email,
            oidc_sub=sub,
            is_active=True,
            created_at=utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        add_audit_log(db, "oidc", "create", "user", user.user_id, username)
    else:
        user.oidc_sub = sub
        db.commit()
        db.refresh(user)
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
    deliver_external(
        db,
        message=message,
        recipient_role=recipient_role,
        recipient_username=recipient_username,
    )
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


# ---------------------------------------------------------------------------
# Site feedback
# ---------------------------------------------------------------------------

def create_site_feedback(
    db: Session, feedback: schemas.SiteFeedbackCreate, actor: str
):
    db_feedback = models.SiteFeedback(
        feedback_id=_new_id(),
        created_at=utcnow(),
        created_by=actor,
        status="open",
        **feedback.model_dump(),
    )
    db.add(db_feedback)
    db.commit()
    db.refresh(db_feedback)
    add_audit_log(db, actor, "create", "site_feedback", db_feedback.feedback_id)
    project = get_project(db, feedback.project_id)
    add_notification(
        db,
        message=f"現場フィードバックが登録されました: {project.name if project else feedback.project_id} / {db_feedback.content[:60]}",
        recipient_role="reviewer",
    )
    return db_feedback


def list_site_feedbacks(
    db: Session,
    project_id: Optional[str] = None,
    target_month: Optional[str] = None,
    status: Optional[str] = None,
):
    query = db.query(models.SiteFeedback)
    if project_id:
        query = query.filter(models.SiteFeedback.project_id == project_id)
    if target_month:
        query = query.filter(models.SiteFeedback.target_month == target_month)
    if status:
        query = query.filter(models.SiteFeedback.status == status)
    return query.order_by(models.SiteFeedback.created_at.desc()).all()


def get_site_feedback(db: Session, feedback_id: str):
    return (
        db.query(models.SiteFeedback)
        .filter(models.SiteFeedback.feedback_id == feedback_id)
        .first()
    )


def update_site_feedback(
    db: Session,
    feedback_id: str,
    updates: schemas.SiteFeedbackUpdate,
    actor: str,
):
    feedback = get_site_feedback(db, feedback_id)
    if not feedback:
        return None
    for key, value in updates.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(feedback, key, value)
    feedback.updated_at = utcnow()
    feedback.updated_by = actor
    db.commit()
    db.refresh(feedback)
    add_audit_log(db, actor, "update", "site_feedback", feedback_id)
    return feedback


def delete_site_feedback(db: Session, feedback_id: str, actor: str) -> bool:
    feedback = get_site_feedback(db, feedback_id)
    if not feedback:
        return False
    db.delete(feedback)
    db.commit()
    add_audit_log(db, actor, "delete", "site_feedback", feedback_id)
    return True


# ---------------------------------------------------------------------------
# SBTi targets
# ---------------------------------------------------------------------------

def create_sbti_target(db: Session, target: schemas.SbtiTargetCreate, actor: str):
    db_target = models.SbtiTarget(
        target_id=_new_id(),
        created_at=utcnow(),
        is_active=True,
        **target.model_dump(),
    )
    db.add(db_target)
    db.commit()
    db.refresh(db_target)
    add_audit_log(db, actor, "create", "sbti_target", db_target.target_id, db_target.name)
    return db_target


def list_sbti_targets(db: Session) -> list[models.SbtiTarget]:
    return db.query(models.SbtiTarget).order_by(
        models.SbtiTarget.scope, models.SbtiTarget.base_year
    ).all()


def get_sbti_target(db: Session, target_id: str):
    return (
        db.query(models.SbtiTarget)
        .filter(models.SbtiTarget.target_id == target_id)
        .first()
    )


def update_sbti_target(
    db: Session,
    target_id: str,
    updates: schemas.SbtiTargetUpdate,
    actor: str,
):
    target = get_sbti_target(db, target_id)
    if not target:
        return None
    for key, value in updates.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(target, key, value)
    target.updated_at = utcnow()
    db.commit()
    db.refresh(target)
    add_audit_log(db, actor, "update", "sbti_target", target_id)
    return target


def delete_sbti_target(db: Session, target_id: str, actor: str) -> bool:
    target = get_sbti_target(db, target_id)
    if not target:
        return False
    db.delete(target)
    db.commit()
    add_audit_log(db, actor, "delete", "sbti_target", target_id)
    return True


# ---------------------------------------------------------------------------
# Monthly close (locking)
# ---------------------------------------------------------------------------

def is_month_closed(db: Session, project_id: str, target_month: str) -> bool:
    return (
        db.query(models.MonthlyClose)
        .filter(
            models.MonthlyClose.project_id == project_id,
            models.MonthlyClose.target_month == target_month,
        )
        .first()
        is not None
    )


def create_monthly_close(
    db: Session, body: schemas.MonthlyCloseCreate, actor: str
) -> models.MonthlyClose:
    if is_month_closed(db, body.project_id, body.target_month):
        raise ValueError("Month already closed")
    close = models.MonthlyClose(
        close_id=_new_id(),
        project_id=body.project_id,
        target_month=body.target_month,
        note=body.note,
        closed_by=actor,
        closed_at=utcnow(),
    )
    db.add(close)
    db.commit()
    db.refresh(close)
    add_audit_log(db, actor, "create", "monthly_close", close.close_id, f"{body.project_id}/{body.target_month}")
    project = get_project(db, body.project_id)
    add_notification(
        db,
        message=f"月次締めが完了しました: {project.name if project else body.project_id} / {body.target_month}",
        recipient_role="site",
    )
    return close


def list_monthly_closes(
    db: Session, project_id: Optional[str] = None, target_month: Optional[str] = None
) -> list[models.MonthlyClose]:
    query = db.query(models.MonthlyClose)
    if project_id:
        query = query.filter(models.MonthlyClose.project_id == project_id)
    if target_month:
        query = query.filter(models.MonthlyClose.target_month == target_month)
    return query.order_by(models.MonthlyClose.closed_at.desc()).all()


def delete_monthly_close(db: Session, close_id: str, actor: str) -> bool:
    close = db.query(models.MonthlyClose).filter(models.MonthlyClose.close_id == close_id).first()
    if not close:
        return False
    db.delete(close)
    db.commit()
    add_audit_log(db, actor, "delete", "monthly_close", close_id)
    return True


# ---------------------------------------------------------------------------
# Activity comments
# ---------------------------------------------------------------------------

def add_activity_comment(
    db: Session, activity_id: str, content: str, actor: str
) -> models.ActivityComment:
    comment = models.ActivityComment(
        comment_id=_new_id(),
        activity_id=activity_id,
        author=actor,
        content=content,
        created_at=utcnow(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    activity = get_activity(db, activity_id)
    if activity:
        recipient_role = "reviewer" if actor == activity.created_by else "site"
        add_notification(
            db,
            message=f"活動量にコメント: {activity.item_name} / {comment.content[:60]}",
            recipient_role=recipient_role,
        )
    return comment


def list_activity_comments(db: Session, activity_id: str) -> list[models.ActivityComment]:
    return (
        db.query(models.ActivityComment)
        .filter(models.ActivityComment.activity_id == activity_id)
        .order_by(models.ActivityComment.created_at.asc())
        .all()
    )


def delete_activity_comment(db: Session, comment_id: str, actor: str) -> bool:
    comment = (
        db.query(models.ActivityComment)
        .filter(models.ActivityComment.comment_id == comment_id)
        .first()
    )
    if not comment:
        return False
    db.delete(comment)
    db.commit()
    add_audit_log(db, actor, "delete", "activity_comment", comment_id)
    return True


# ---------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------

def create_branch(db: Session, name: str, actor: str) -> models.Branch:
    existing = (
        db.query(models.Branch).filter(models.Branch.name == name).first()
    )
    if existing:
        raise ValueError("Branch already exists")
    branch = models.Branch(
        branch_id=_new_id(),
        name=name,
        created_at=utcnow(),
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    add_audit_log(db, actor, "create", "branch", branch.branch_id, name)
    return branch


def list_branches(db: Session) -> list[models.Branch]:
    return db.query(models.Branch).order_by(models.Branch.name).all()


def delete_branch(db: Session, branch_id: str, actor: str) -> bool:
    branch = db.query(models.Branch).filter(models.Branch.branch_id == branch_id).first()
    if not branch:
        return False
    db.delete(branch)
    db.commit()
    add_audit_log(db, actor, "delete", "branch", branch_id)
    return True


# ---------------------------------------------------------------------------
# User-project access (client portal)
# ---------------------------------------------------------------------------

def set_user_project_access(
    db: Session, user_id: str, project_ids: list[str], actor: str
) -> list[models.UserProjectAccess]:
    db.query(models.UserProjectAccess).filter(
        models.UserProjectAccess.user_id == user_id
    ).delete()
    created = []
    for pid in project_ids:
        access = models.UserProjectAccess(
            access_id=_new_id(),
            user_id=user_id,
            project_id=pid,
            created_by=actor,
            created_at=utcnow(),
        )
        db.add(access)
        created.append(access)
    db.commit()
    add_audit_log(db, actor, "update", "user_project_access", user_id, f"{len(project_ids)} projects")
    return created


def accessible_project_ids(db: Session, user: models.User) -> list[str]:
    if user.role == "client":
        return [
            a.project_id
            for a in db.query(models.UserProjectAccess)
            .filter(models.UserProjectAccess.user_id == user.user_id)
            .all()
        ]
    return [p.project_id for p in list_projects(db)]


def has_project_access(db: Session, user: models.User, project_id: str) -> bool:
    if user.role != "client":
        return True
    return (
        db.query(models.UserProjectAccess)
        .filter(
            models.UserProjectAccess.user_id == user.user_id,
            models.UserProjectAccess.project_id == project_id,
        )
        .first()
        is not None
    )


def list_projects_for_user(db: Session, user: models.User) -> list[models.Project]:
    projects = list_projects(db)
    if user.role == "site" and user.branch:
        projects = [p for p in projects if p.branch == user.branch]
    if user.role == "client":
        allowed = set(accessible_project_ids(db, user))
        projects = [p for p in projects if p.project_id in allowed]
    return projects


# ---------------------------------------------------------------------------
# Copy previous month & reminders
# ---------------------------------------------------------------------------

def copy_previous_month(
    db: Session, project_id: str, from_month: str, to_month: str, actor: str
) -> dict:
    sources = list_activity_data(db, project_id=project_id, target_month=from_month)
    copied = 0
    skipped = 0
    errors: list[str] = []
    existing_keys = {
        (a.category, a.item_name, a.unit)
        for a in list_activity_data(db, project_id=project_id, target_month=to_month)
    }
    for src in sources:
        key = (src.category, src.item_name, src.unit)
        if key in existing_keys:
            skipped += 1
            continue
        try:
            create_activity_data(
                db,
                schemas.ActivityDataCreate(
                    project_id=project_id,
                    target_month=to_month,
                    category=src.category,
                    item_name=src.item_name,
                    quantity=src.quantity,
                    unit=src.unit,
                    source_file=f"前月コピー: {from_month}",
                    note=src.note,
                    supplier=src.supplier,
                    created_by=actor,
                ),
                actor=actor,
            )
            copied += 1
        except ValueError as e:
            errors.append(str(e))
            skipped += 1
    return {"copied": copied, "skipped": skipped, "errors": errors}


def get_monthly_reminders(db: Session, target_month: str) -> list[dict]:
    reminders = []
    for project in list_projects(db):
        activities = list_activity_data(
            db, project_id=project.project_id, target_month=target_month
        )
        if not activities:
            reminders.append({
                "project_id": project.project_id,
                "project_name": project.name,
                "branch": project.branch,
                "status": "no_data",
                "activity_count": 0,
            })
        else:
            unapproved = [a for a in activities if not a.approved]
            if unapproved:
                reminders.append({
                    "project_id": project.project_id,
                    "project_name": project.name,
                    "branch": project.branch,
                    "status": "unapproved",
                    "activity_count": len(unapproved),
                })
    return reminders


def get_month_status(db: Session, target_month: str) -> list[dict]:
    """Per-project monthly status with close deadline (PoC schedule view)."""
    items = []
    for project in list_projects(db):
        activities = list_activity_data(
            db, project_id=project.project_id, target_month=target_month
        )
        closed = is_month_closed(db, project.project_id, target_month)
        close_day = project.close_day or 25
        year, month = (int(x) for x in target_month.split("-"))
        from datetime import date
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        close_date = date(year, month, min(close_day, last_day))
        today = date.today()
        days_remaining = (close_date - today).days
        items.append({
            "project_id": project.project_id,
            "project_name": project.name,
            "branch": project.branch,
            "close_day": close_day,
            "activity_count": len(activities),
            "approved_count": len([a for a in activities if a.approved]),
            "is_closed": closed,
            "days_remaining": days_remaining,
        })
    return items


# ---------------------------------------------------------------------------
# Offset credits (J-credit / certificates)
# ---------------------------------------------------------------------------

def create_offset_credit(
    db: Session, body: schemas.OffsetCreditCreate, actor: str
) -> models.OffsetCredit:
    if body.credit_type not in {"j_credit", "certificate", "other"}:
        raise ValueError("Invalid credit_type")
    credit = models.OffsetCredit(
        credit_id=_new_id(),
        status="available",
        created_by=actor,
        created_at=utcnow(),
        **body.model_dump(),
    )
    db.add(credit)
    db.commit()
    db.refresh(credit)
    add_audit_log(db, actor, "create", "offset_credit", credit.credit_id, credit.name)
    return credit


def list_offset_credits(db: Session, status: Optional[str] = None):
    query = db.query(models.OffsetCredit)
    if status:
        query = query.filter(models.OffsetCredit.status == status)
    return query.order_by(models.OffsetCredit.created_at.desc()).all()


def get_offset_credit(db: Session, credit_id: str):
    return (
        db.query(models.OffsetCredit)
        .filter(models.OffsetCredit.credit_id == credit_id)
        .first()
    )


def delete_offset_credit(db: Session, credit_id: str, actor: str) -> bool:
    credit = get_offset_credit(db, credit_id)
    if not credit:
        return False
    db.delete(credit)
    db.commit()
    add_audit_log(db, actor, "delete", "offset_credit", credit_id)
    return True


def allocate_offset_credit(
    db: Session, credit_id: str, project_id: str, quantity_tco2: float, actor: str
) -> models.OffsetCredit:
    credit = get_offset_credit(db, credit_id)
    if not credit:
        raise ValueError("Credit not found")
    if credit.status != "available":
        raise ValueError("Credit is not available")
    available = credit.quantity_tco2 - (credit.allocated_tco2 or 0.0)
    if quantity_tco2 > available:
        raise ValueError("Allocation exceeds available quantity")
    credit.allocated_tco2 = (credit.allocated_tco2 or 0.0) + quantity_tco2
    if credit.allocated_tco2 >= credit.quantity_tco2 - 1e-9:
        credit.status = "allocated"
    credit.allocated_project_id = project_id
    credit.allocated_at = utcnow()
    credit.note = (credit.note or "") + f"；{actor} が {project_id} に充当"
    db.commit()
    db.refresh(credit)
    add_audit_log(db, actor, "update", "offset_credit", credit_id, "allocated")
    return credit


def retire_offset_credit(db: Session, credit_id: str, actor: str) -> models.OffsetCredit:
    credit = get_offset_credit(db, credit_id)
    if not credit:
        raise ValueError("Credit not found")
    if credit.status == "retired":
        raise ValueError("Credit already retired")
    credit.status = "retired"
    db.commit()
    db.refresh(credit)
    add_audit_log(db, actor, "update", "offset_credit", credit_id, "retired")
    return credit


def offset_summary(db: Session) -> dict:
    totals = {"available": 0.0, "allocated": 0.0, "retired": 0.0}
    for credit in list_offset_credits(db):
        if credit.status == "retired":
            totals["retired"] += credit.quantity_tco2
        else:
            totals["allocated"] += credit.allocated_tco2 or 0.0
            totals["available"] += credit.quantity_tco2 - (credit.allocated_tco2 or 0.0)
    return {
        "available_tco2": totals["available"],
        "allocated_tco2": totals["allocated"],
        "retired_tco2": totals["retired"],
        "total_tco2": sum(totals.values()),
    }


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
