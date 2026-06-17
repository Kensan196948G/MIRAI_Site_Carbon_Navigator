from sqlalchemy import (
    Column,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
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

    project = relationship("Project")


class EmissionResult(Base):
    __tablename__ = "emission_results"

    result_id = Column(String, primary_key=True)
    activity_id = Column(String, ForeignKey("activity_data.activity_id"))
    factor_id = Column(String, ForeignKey("emission_factors.factor_id"))
    co2_kg = Column(Float)
    calculated_at = Column(DateTime(timezone=True))

    activity = relationship("ActivityData")
    factor = relationship("EmissionFactor")
