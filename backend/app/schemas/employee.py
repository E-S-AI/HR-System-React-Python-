from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.excel_utils import to_national_id, to_phone

EMPLOYMENT_TYPES = ("مثبت", "متعاقد")

# أطوال أعمدة قاعدة البيانات (تجاوزها يعطي خطأ 422 واضحاً بدل خطأ خادم)
MAX_LEN = {
    "governorate_code": 10, "appointment_category_code": 10, "biometric_code": 50,
    "first_name": 100, "father_name": 100, "last_name": 100, "mother_full_name": 200,
    "national_id": 50, "gender": 20, "birth_place": 150, "country": 100,
    "civil_reg_governorate": 100, "civil_reg_secretariat": 150, "civil_reg_place": 150,
    "civil_reg_number": 50, "marital_status": 50, "residence_governorate": 100,
    "residence_city_region": 150, "job_title_name": 200, "job_classification": 150,
    "current_job_category": 50, "job_rank": 50, "job_grade": 50,
    "employment_pattern": 150, "employment_status": 100, "assignment_duration": 100,
    "phone_number": 30, "electronic_account": 150, "sham_cash_account": 100,
    "children_details": 5000, "residence_address_detail": 5000, "status_details": 5000,
    "merger_details": 5000, "qualifications_excel_raw": 5000,
    "addition_request_info": 5000, "central_notes": 5000,
}


class EmployeeShape(BaseModel):
    """كل الحقول القابلة للإدخال والتعديل (كلها اختيارية هنا)."""

    governorate_code: str | None = None
    appointment_category_code: str | None = None
    biometric_code: str | None = None
    self_registry_number: int | None = None

    first_name: str | None = None
    father_name: str | None = None
    last_name: str | None = None
    mother_full_name: str | None = None
    national_id: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    birth_place: str | None = None

    country: str | None = None
    civil_reg_governorate: str | None = None
    civil_reg_secretariat: str | None = None
    civil_reg_place: str | None = None
    civil_reg_number: str | None = None
    marital_status: str | None = None
    wives_count: int | None = None
    children_count: int | None = None
    children_details: str | None = None
    residence_governorate: str | None = None
    residence_city_region: str | None = None
    residence_address_detail: str | None = None

    org_unit_id: int | None = None

    job_title_name: str | None = None
    job_classification: str | None = None
    current_job_category: str | None = None
    job_rank: str | None = None
    job_grade: str | None = None
    permanent_or_contract: str | None = None
    employment_pattern: str | None = None
    employment_status: str | None = None
    status_details: str | None = None
    merger_details: str | None = None
    qualifications_excel_raw: str | None = None

    state_start_date: date | None = None
    hire_date: date | None = None
    work_start_date: date | None = None
    ministry_start_date: date | None = None
    termination_date: date | None = None
    assignment_start_date: date | None = None
    assignment_end_date: date | None = None
    assignment_duration: str | None = None
    assignment_renewal_count: int | None = None

    phone_number: str | None = None
    electronic_account: str | None = None
    sham_cash_account: str | None = None
    addition_request_info: str | None = None
    central_notes: str | None = None


class EmployeeInput(EmployeeShape):
    model_config = ConfigDict(extra="forbid")  # حقل غير معروف (مثل employee_code) يُرفض

    @field_validator("*", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @model_validator(mode="after")
    def check_values(self):
        for name, limit in MAX_LEN.items():
            v = getattr(self, name, None)
            if isinstance(v, str) and len(v) > limit:
                raise ValueError(f"الحقل {name} أطول من {limit} حرفاً")
        if (
            self.permanent_or_contract is not None
            and self.permanent_or_contract not in EMPLOYMENT_TYPES
        ):
            raise ValueError("مثبت او متعاقد: القيمة يجب أن تكون (مثبت) أو (متعاقد)")
        for name in ("wives_count", "children_count", "assignment_renewal_count"):
            v = getattr(self, name)
            if v is not None and v < 0:
                raise ValueError(f"{name} لا يكون سالباً")
        if self.national_id is not None:
            self.national_id = to_national_id(self.national_id)
        if self.phone_number is not None:
            phone = to_phone(self.phone_number)
            if phone is None:
                raise ValueError("رقم الهاتف غير صالح")
            self.phone_number = phone
        return self


class QualificationIn(BaseModel):
    qualification_level: str = Field(min_length=1, max_length=100)
    specialization: str | None = Field(default=None, max_length=150)
    issuing_institution: str | None = Field(default=None, max_length=150)
    graduation_year: str | None = Field(default=None, max_length=20)
    is_hiring_qualification: bool = False
    notes: str | None = Field(default=None, max_length=5000)


class TrainingIn(BaseModel):
    course_name: str = Field(min_length=1, max_length=200)
    training_provider: str | None = Field(default=None, max_length=150)
    course_date: str | None = Field(default=None, max_length=50)
    duration_text: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=5000)


class AccountOptions(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class EmployeeCreate(EmployeeInput):
    governorate_code: str
    first_name: str
    last_name: str
    phone_number: str
    state_start_date: date

    qualifications: list[QualificationIn] = Field(default_factory=list, max_length=50)
    trainings: list[TrainingIn] = Field(default_factory=list, max_length=50)
    create_account: AccountOptions | None = None
    grant_leave_balance: bool = False

    @model_validator(mode="after")
    def one_hiring_qualification(self):
        if sum(1 for q in self.qualifications if q.is_hiring_qualification) > 1:
            raise ValueError("يُسمح بمؤهل تعيين واحد فقط")
        return self


class EmployeePatch(EmployeeInput):
    change_reason: str | None = Field(default=None, max_length=255)


class CategoryAssign(BaseModel):
    category_code: str


# ------------------------------------------------------------------ القراءة
class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    global_serial_number: int
    formatted_serial: str
    employee_code: str | None
    governorate_code: str
    org_unit_id: int | None
    appointment_category_code: str | None
    biometric_code: str | None
    first_name: str
    father_name: str | None
    last_name: str
    full_name_spaced: str
    national_id: str | None
    phone_number: str
    job_title_name: str | None
    permanent_or_contract: str
    employment_status: str | None
    state_start_date: date
    termination_date: date | None
    created_at: datetime


class QualificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    qualification_level: str
    specialization: str | None
    issuing_institution: str | None
    graduation_year: str | None
    is_hiring_qualification: bool
    notes: str | None


class TrainingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_name: str
    training_provider: str | None
    course_date: str | None
    duration_text: str | None
    notes: str | None


class EmployeeDetail(EmployeeShape):
    model_config = ConfigDict(from_attributes=True)

    id: int
    global_serial_number: int
    formatted_serial: str
    employee_code: str | None = None
    full_name_spaced: str = ""
    full_name_underscored: str | None = None
    age: int | None = None
    org_levels_import_raw: dict | None = None
    qualifications: list[QualificationRead] = []
    trainings: list[TrainingRead] = []
    account_user_id: int | None = None
    account_active: bool | None = None
    created_at: datetime
    updated_at: datetime
    updated_by_hr_id: int | None = None


class AccountResult(BaseModel):
    user_id: int
    phone_number: str
    static_pin: str  # يظهر مرة واحدة فقط


class EmployeeCreated(BaseModel):
    employee: EmployeeDetail
    account: AccountResult | None = None
    balance_granted: bool = False
    warnings: list[str] = []


class EmployeePatchResult(BaseModel):
    employee: EmployeeDetail
    changed_fields: list[str]
    balances_recalculated: int = 0
    account_deactivated: bool = False


class ChangeLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    field_name: str
    old_value: str | None
    new_value: str | None
    change_reason: str | None
    changed_by_user_id: int
    changed_at: datetime