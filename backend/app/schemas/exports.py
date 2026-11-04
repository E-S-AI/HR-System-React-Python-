from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmployeeExportFilters(BaseModel):
    governorate_code: str | None = None
    org_unit_id: int | None = None
    include_sub_units: bool = True
    permanent_or_contract: str | None = None
    appointment_category_code: str | None = None
    employment_status: str | None = None
    has_account: bool | None = None
    state_start_from: date | None = None
    state_start_to: date | None = None
    search: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class EmployeeExportRequest(BaseModel):
    filters: EmployeeExportFilters = Field(default_factory=EmployeeExportFilters)
    columns: list[str] | None = None


class ExportColumnRead(BaseModel):
    key: str
    label: str
    default: bool


class ExportLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exported_by_user_id: int
    module_name: str
    applied_filters: dict | None
    selected_columns: list | None
    exported_rows_count: int
    exported_at: datetime