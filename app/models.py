from sqlalchemy import (
    Column,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship
from .database import Base


class Project(Base):
    __tablename__ = "projects"

    project_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    branch = Column(String)
    work_type = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True))
    created_by = Column(String)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(String, nullable=True)

    activities = relationship("ActivityData", back_populates="project")


class EmissionFactor(Base):
    __tablename__ = "emission_factors"

    factor_id = Column(String, primary_key=True)
    category = Column(String)
    item_name = Column(String)
    unit = Column(String)
    factor_value = Column(Float)
    effective_from = Column(Date)
    source = Column(String)
    created_at = Column(DateTime(timezone=True))
    created_by = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(String, nullable=True)


class ActivityData(Base):
    __tablename__ = "activity_data"

    activity_id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.project_id"))
    target_month = Column(String)
    category = Column(String)
    item_name = Column(String)
    quantity = Column(Float)
    unit = Column(String)
    source_file = Column(String, nullable=True)
    approved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True))
    created_by = Column(String)
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(String, nullable=True)

    project = relationship("Project", back_populates="activities")


class EmissionResult(Base):
    __tablename__ = "emission_results"

    result_id = Column(String, primary_key=True)
    activity_id = Column(String, ForeignKey("activity_data.activity_id"))
    factor_id = Column(String, ForeignKey("emission_factors.factor_id"))
    co2_kg = Column(Float)
    calculated_at = Column(DateTime(timezone=True))
    factor_value = Column(Float, nullable=True)
    factor_source = Column(String, nullable=True)
    factor_effective_from = Column(Date, nullable=True)
    item_name = Column(String, nullable=True)
    unit = Column(String, nullable=True)

    activity = relationship("ActivityData")
    factor = relationship("EmissionFactor")


class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="viewer")  # admin/reviewer/site/viewer
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True))


class ReductionAction(Base):
    __tablename__ = "reduction_actions"

    action_id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.project_id"), nullable=False)
    target_month = Column(String, nullable=False)
    category = Column(String, nullable=False)
    suggestion = Column(Text, nullable=False)
    status = Column(String, default="planned")  # planned/implemented/declined
    estimated_reduction_kg = Column(Float, nullable=True)
    actual_reduction_kg = Column(Float, nullable=True)
    note = Column(Text, nullable=True)
    created_by = Column(String)
    created_at = Column(DateTime(timezone=True))
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id = Column(String, primary_key=True)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)      # create/update/delete/approve/login
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True))
