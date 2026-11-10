from datetime import date, datetime
from pydantic import BaseModel


class WorkforceKPIs(BaseModel):
    total_employees: int
    active_employees: int
    terminated_employees: int
    permanent_count: int
    contract_count: int
    missing_code_count: int
    missing_biometric_count: int
    with_account_count: int


class LeaveKPIs(BaseModel):
    pending_hr_approval: int
    awaiting_paper: int
    expiring_within_12h: int
    on_leave_today: int
    on_mission_today: int


class ExpiringAssignmentItem(BaseModel):
    employee_id: int
    full_name_spaced: str
    employee_code: str | None
    governorate_code: str
    assignment_end_date: date
    days_remaining: int


class LockedUserItem(BaseModel):
    user_id: int
    phone_number: str
    employee_id: int | None
    employee_name: str | None
    locked_until: datetime


class ExpiringLeaveItem(BaseModel):
    request_id: int
    employee_id: int
    employee_name: str
    leave_type_name_ar: str
    attachment_deadline_at: datetime
    hours_remaining: float


class PendingLeaveBrief(BaseModel):
    request_id: int
    employee_id: int
    employee_name: str
    employee_code: str | None
    governorate_code: str
    leave_type_code: str
    leave_type_name_ar: str
    start_date: date
    end_date: date
    duration_days: float
    duration_minutes: int
    attachment_uploaded_at: datetime | None


class AlertsCenter(BaseModel):
    expiring_assignments: list[ExpiringAssignmentItem]
    locked_users: list[LockedUserItem]
    expiring_leaves_12h: list[ExpiringLeaveItem]


class DistributionItem(BaseModel):
    code: str
    label_ar: str
    count: int


class RecentImportBrief(BaseModel):
    job_id: int
    original_file_name: str
    status: str
    total_rows: int
    valid_new_rows: int
    error_rows: int
    created_at: datetime


class DashboardSummary(BaseModel):
    workforce: WorkforceKPIs
    leaves: LeaveKPIs
    alerts: AlertsCenter
    by_governorate: list[DistributionItem]
    by_category: list[DistributionItem]
    recent_pending_leaves: list[PendingLeaveBrief]
    recent_imports: list[RecentImportBrief]