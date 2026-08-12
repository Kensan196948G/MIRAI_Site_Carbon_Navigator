import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectCreate(BaseModel):
    name: str
    branch: str
    work_type: str
    start_date: datetime.date
    end_date: datetime.date
    description: str | None = None
    close_day: int | None = Field(default=None, ge=1, le=28)
    created_by: str = "system"


class ProjectUpdate(BaseModel):
    name: str | None = None
    branch: str | None = None
    work_type: str | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    description: str | None = None
    close_day: int | None = Field(default=None, ge=1, le=28)


class ProjectRead(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    project_id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime | None = None
    updated_by: str | None = None


class EmissionFactorCreate(BaseModel):
    category: str
    item_name: str
    unit: str
    factor_value: float
    effective_from: datetime.date
    source: str
    supplier: str | None = None


class EmissionFactorUpdate(BaseModel):
    category: str | None = None
    item_name: str | None = None
    unit: str | None = None
    factor_value: float | None = None
    effective_from: datetime.date | None = None
    source: str | None = None
    supplier: str | None = None


class EmissionFactorRead(EmissionFactorCreate):
    model_config = ConfigDict(from_attributes=True)
    factor_id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime | None = None
    updated_by: str | None = None


class ActivityDataCreate(BaseModel):
    project_id: str
    target_month: str
    category: str
    item_name: str
    quantity: float
    unit: str
    source_file: str | None = None
    created_by: str = "system"
    note: str | None = None
    supplier: str | None = None

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
    category: str | None = None
    item_name: str | None = None
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = None
    source_file: str | None = None
    note: str | None = None
    supplier: str | None = None


class ActivityDataRead(ActivityDataCreate):
    model_config = ConfigDict(from_attributes=True)
    activity_id: str
    approved: bool
    approval_status: str = "draft"
    created_at: datetime.datetime
    approved_by: str | None = None
    approved_at: datetime.datetime | None = None
    updated_by: str | None = None
    updated_at: datetime.datetime | None = None


class ActivityDataApprove(BaseModel):
    approved: bool = True


class EmissionResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    result_id: str
    activity_id: str
    factor_id: str
    co2_kg: float
    calculated_at: datetime.datetime
    factor_value: float | None = None
    factor_source: str | None = None
    factor_effective_from: datetime.date | None = None
    item_name: str | None = None
    unit: str | None = None


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


class BenchmarkItem(BaseModel):
    project_id: str
    target_month: str
    work_type: str | None = None
    current_total_kg: float
    current_total_t: float
    current_by_category: dict[str, float]
    peer_project_count: int
    peer_avg_monthly_kg: float | None = None
    peer_avg_monthly_t: float | None = None
    peer_by_category: dict[str, float]
    comparison_ratio: float | None = None


class AnomalyItem(BaseModel):
    activity_id: str
    category: str
    item_name: str
    quantity: float
    unit: str
    reasons: list[str]


class ReductionSuggestion(BaseModel):
    category: str
    total_co2_kg: float
    rank: int
    suggestions: list[str]


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=10)
    display_name: str | None = None
    role: str = "viewer"
    branch: str | None = None
    email: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: str | None = None
    password: str | None = Field(default=None, min_length=10)
    is_active: bool | None = None
    branch: str | None = None
    email: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    username: str
    display_name: str | None = None
    role: str
    branch: str | None = None
    email: str | None = None
    is_2fa_enabled: bool = False
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
    estimated_reduction_kg: float | None = None
    actual_reduction_kg: float | None = None
    note: str | None = None


class ReductionActionUpdate(BaseModel):
    status: str | None = None
    suggestion: str | None = None
    estimated_reduction_kg: float | None = None
    actual_reduction_kg: float | None = None
    note: str | None = None


class ReductionActionRead(ReductionActionCreate):
    model_config = ConfigDict(from_attributes=True)
    action_id: str
    created_by: str
    created_at: datetime.datetime
    updated_by: str | None = None
    updated_at: datetime.datetime | None = None


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    log_id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str | None = None
    detail: str | None = None
    created_at: datetime.datetime


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    notification_id: str
    recipient_role: str | None = None
    recipient_username: str | None = None
    message: str
    link: str | None = None
    is_read: bool
    created_at: datetime.datetime


class SiteFeedbackCreate(BaseModel):
    project_id: str
    target_month: str
    category: str | None = None
    content: str


class SiteFeedbackUpdate(BaseModel):
    content: str | None = None
    status: str | None = None


class SiteFeedbackRead(SiteFeedbackCreate):
    model_config = ConfigDict(from_attributes=True)
    feedback_id: str
    status: str
    created_by: str
    created_at: datetime.datetime
    updated_by: str | None = None
    updated_at: datetime.datetime | None = None


class SbtiTargetCreate(BaseModel):
    scope: str
    name: str
    description: str | None = None
    base_year: int
    target_year: int
    base_emissions_kg: float
    reduction_percent: float


class SbtiTargetUpdate(BaseModel):
    scope: str | None = None
    name: str | None = None
    description: str | None = None
    base_year: int | None = None
    target_year: int | None = None
    base_emissions_kg: float | None = None
    reduction_percent: float | None = None
    is_active: bool | None = None


class SbtiTargetRead(SbtiTargetCreate):
    model_config = ConfigDict(from_attributes=True)
    target_id: str
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime | None = None


class SbtiProgressItem(SbtiTargetRead):
    target_emissions_kg: float
    current_emissions_kg: float
    reduction_achieved_percent: float
    progress_ratio: float | None = None
    on_track: bool


class ScopeSummaryItem(BaseModel):
    scope: str
    label: str
    total_co2_kg: float
    total_co2_t: float
    by_category: dict[str, float]


class DemoGenerateResult(BaseModel):
    project_count: int
    activity_count: int
    result_count: int
    action_count: int
    feedback_count: int
    projects: list[str]


class MonthlyCloseCreate(BaseModel):
    project_id: str
    target_month: str
    note: str | None = None


class MonthlyCloseRead(MonthlyCloseCreate):
    model_config = ConfigDict(from_attributes=True)
    close_id: str
    closed_by: str
    closed_at: datetime.datetime


class ActivityCommentCreate(BaseModel):
    content: str


class ActivityCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    comment_id: str
    activity_id: str
    author: str
    content: str
    created_at: datetime.datetime


class BranchCreate(BaseModel):
    name: str


class BranchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    branch_id: str
    name: str
    created_at: datetime.datetime


class CopyPreviousRequest(BaseModel):
    project_id: str
    from_month: str
    to_month: str


class CopyPreviousResult(BaseModel):
    copied: int
    skipped: int
    errors: list[str]


class ReminderItem(BaseModel):
    project_id: str
    project_name: str
    branch: str | None = None
    status: str  # no_data / unapproved
    activity_count: int


class ReminderSendRequest(BaseModel):
    target_month: str


class UnitConvertRequest(BaseModel):
    value: float
    from_unit: str
    to_unit: str


class UnitConvertResult(BaseModel):
    value: float
    from_unit: str
    to_unit: str
    converted_value: float
    conversion_factor: float


class TelematicsImportRequest(BaseModel):
    project_id: str
    target_month: str


class TelematicsImportResult(BaseModel):
    imported: int
    skipped: int
    provider: str
    items: list[dict]


class UserProjectAccessCreate(BaseModel):
    user_id: str
    project_ids: list[str]


class UserProjectAccessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    access_id: str
    user_id: str
    project_id: str
    created_by: str
    created_at: datetime.datetime


class ProjectImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


class ComparisonItem(BaseModel):
    current_total_kg: float
    current_total_t: float
    previous_month_kg: float | None = None
    previous_month_t: float | None = None
    mom_ratio: float | None = None
    previous_year_kg: float | None = None
    previous_year_t: float | None = None
    yoy_ratio: float | None = None


class MissingMonthItem(BaseModel):
    target_month: str
    activity_count: int
    reason: str


class MonthStatusItem(BaseModel):
    project_id: str
    project_name: str
    branch: str | None = None
    close_day: int | None = None
    activity_count: int
    approved_count: int
    is_closed: bool
    days_remaining: int | None = None


class ScenarioAdjustment(BaseModel):
    fuel: float | None = 0.0
    power: float | None = 0.0
    material: float | None = 0.0
    transport: float | None = 0.0
    machine: float | None = 0.0
    ship: float | None = 0.0
    waste: float | None = 0.0
    business_travel: float | None = 0.0
    commuting: float | None = 0.0
    water: float | None = 0.0


class ScenarioRequest(BaseModel):
    project_id: str
    target_month: str | None = None
    adjustments: ScenarioAdjustment


class ScenarioResult(BaseModel):
    current_total_kg: float
    scenario_total_kg: float
    reduction_kg: float
    reduction_t: float
    reduction_percent: float
    by_category: dict[str, dict]
    scope_after: dict[str, float]


class ForecastItem(BaseModel):
    target_month: str
    forecast_total_kg: float
    forecast_total_t: float
    trend_slope_kg_per_month: float


class ActivityChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    change_id: str
    activity_id: str
    actor: str
    field: str
    old_value: str | None = None
    new_value: str | None = None
    co2_kg_before: float | None = None
    co2_kg_after: float | None = None
    created_at: datetime.datetime


class ApprovalAction(BaseModel):
    action: str  # submit / approve_branch / approve_env / reject / withdraw
    comment: str | None = None


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    already_enabled: bool


class TotpVerifyRequest(BaseModel):
    code: str


class LoginResponse(TokenResponse):
    requires_2fa: bool = False
    temp_token: str | None = None


class TotpLoginRequest(BaseModel):
    temp_token: str
    code: str


class OidcExchangeRequest(BaseModel):
    code: str


class OffsetCreditCreate(BaseModel):
    credit_type: str
    name: str
    serial_number: str | None = None
    quantity_tco2: float = Field(gt=0)
    purchased_at: datetime.date | None = None
    note: str | None = None


class OffsetCreditRead(OffsetCreditCreate):
    model_config = ConfigDict(from_attributes=True)
    credit_id: str
    status: str
    allocated_tco2: float = 0.0
    allocated_project_id: str | None = None
    allocated_at: datetime.datetime | None = None
    created_by: str
    created_at: datetime.datetime


class OffsetAllocateRequest(BaseModel):
    project_id: str
    quantity_tco2: float = Field(gt=0)


class OffsetSummary(BaseModel):
    available_tco2: float
    allocated_tco2: float
    retired_tco2: float
    total_tco2: float


class AssistantSuggestion(BaseModel):
    category: str
    title: str
    rationale: str
    actions: list[str]
    confidence: float
    estimated_reduction_kg: float | None = None
