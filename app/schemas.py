from pydantic import BaseModel, ConfigDict
from typing import Optional
import datetime


class ProjectCreate(BaseModel):
    name: str
    branch: str
    work_type: str
    start_date: datetime.date
    end_date: datetime.date
    description: Optional[str] = None
    created_by: str = "system"


class ProjectRead(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    project_id: str
    created_at: datetime.datetime


class EmissionFactorCreate(BaseModel):
    category: str
    item_name: str
    unit: str
    factor_value: float
    effective_from: datetime.date
    source: str


class EmissionFactorRead(EmissionFactorCreate):
    model_config = ConfigDict(from_attributes=True)
    factor_id: str
    created_at: datetime.datetime


class ActivityDataCreate(BaseModel):
    project_id: str
    target_month: str
    category: str
    item_name: str
    quantity: float
    unit: str
    source_file: Optional[str] = None
    created_by: str = "system"


class ActivityDataRead(ActivityDataCreate):
    model_config = ConfigDict(from_attributes=True)
    activity_id: str
    approved: bool
    created_at: datetime.datetime


class ActivityDataApprove(BaseModel):
    approved: bool


class EmissionResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    result_id: str
    activity_id: str
    factor_id: str
    co2_kg: float
    calculated_at: datetime.datetime


class MonthlyReportRow(BaseModel):
    category: str
    item_name: str
    quantity: float
    unit: str
    factor_value: float
    co2_kg: float


class CalculateRequest(BaseModel):
    project_id: str
    target_month: str


class SummaryItem(BaseModel):
    category: str
    total_co2_kg: float


class ReductionSuggestion(BaseModel):
    category: str
    total_co2_kg: float
    rank: int
    suggestions: list[str]
