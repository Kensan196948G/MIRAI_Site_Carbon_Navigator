from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
import datetime
import re


class ProjectCreate(BaseModel):
    name: str
    branch: str
    work_type: str
    start_date: datetime.date
    end_date: datetime.date
    description: Optional[str] = None
    created_by: str = "system"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    branch: Optional[str] = None
    work_type: Optional[str] = None
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    description: Optional[str] = None


class ProjectRead(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    project_id: str
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    updated_by: Optional[str] = None


class EmissionFactorCreate(BaseModel):
    category: str
    item_name: str
    unit: str
    factor_value: float
    effective_from: datetime.date
    source: str


class EmissionFactorUpdate(BaseModel):
    category: Optional[str] = None
    item_name: Optional[str] = None
    unit: Optional[str] = None
    factor_value: Optional[float] = None
    effective_from: Optional[datetime.date] = None
    source: Optional[str] = None


class EmissionFactorRead(EmissionFactorCreate):
    model_config = ConfigDict(from_attributes=True)
    factor_id: str
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None
    updated_by: Optional[str] = None


class ActivityDataCreate(BaseModel):
    project_id: str
    target_month: str
    category: str
    item_name: str
    quantity: float
    unit: str
    source_file: Optional[str] = None
    created_by: str = "system"
    note: Optional[str] = None

    @field_validator("target_month")
    @classmethod
    def validate_month(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", v):
            raise ValueError("target_month must be YYYY-MM")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v


class ActivityDataUpdate(BaseModel):
    category: Optional[str] = None
    item_name: Optional[str] = None
    quantity: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = None
    source_file: Optional[str] = None
    note: Optional[str] = None


class ActivityDataRead(ActivityDataCreate):
    model_config = ConfigDict(from_attributes=True)
    activity_id: str
    approved: bool
    created_at: datetime.datetime
    approved_by: Optional[str] = None
    approved_at: Optional[datetime.datetime] = None
    updated_by: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None


class ActivityDataApprove(BaseModel):
    approved: bool = True


class EmissionResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    result_id: str
    activity_id: str
    factor_id: str
    co2_kg: float
    calculated_at: datetime.datetime
    factor_value: Optional[float] = None
    factor_source: Optional[str] = None
    factor_effective_from: Optional[datetime.date] = None
    item_name: Optional[str] = None
    unit: Optional[str] = None


class CalculationResultItem(EmissionResultRead):
    category: str
    quantity: float


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


class TrendItem(BaseModel):
    target_month: str
    total_co2_kg: float
    total_co2_t: float
    by_category: dict[str, float]


class MissingFactorItem(BaseModel):
    activity_id: str
    category: str
    item_name: str
    quantity: float
    unit: str


class ReductionSuggestion(BaseModel):
    category: str
    total_co2_kg: float
    rank: int
    suggestions: list[str]


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=6)
    display_name: Optional[str] = None
    role: str = "viewer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    username: str
    display_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime.datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class ReductionActionCreate(BaseModel):
    project_id: str
    target_month: str
    category: str
    suggestion: str
    status: str = "planned"
    estimated_reduction_kg: Optional[float] = None
    actual_reduction_kg: Optional[float] = None
    note: Optional[str] = None


class ReductionActionUpdate(BaseModel):
    status: Optional[str] = None
    suggestion: Optional[str] = None
    estimated_reduction_kg: Optional[float] = None
    actual_reduction_kg: Optional[float] = None
    note: Optional[str] = None


class ReductionActionRead(ReductionActionCreate):
    model_config = ConfigDict(from_attributes=True)
    action_id: str
    created_by: str
    created_at: datetime.datetime
    updated_by: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    log_id: str
    actor: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime.datetime


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]
