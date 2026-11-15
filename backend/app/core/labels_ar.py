"""
Arabic labels for status codes, action types, transaction types and field names.
Used in read schemas and validation messages.
"""

# Leave request statuses
STATUS_LABELS_AR = {
    "AWAITING_PAPER": "بانتظار رفع الورقة الموقعة",
    "PENDING_HR_APPROVAL": "بانتظار اعتماد الموارد البشرية",
    "APPROVED": "معتمد",
    "REJECTED_BY_HR": "مرفوض من الموارد البشرية",
    "REJECTED_PAST_72H_DATE": "مرفوض: التاريخ أقدم من 72 ساعة",
    "AUTO_REJECTED_72H_NO_PAPER": "مرفوض آلياً: لم تُرفع الورقة خلال 72 ساعة",
    "CANCELLED_BY_EMPLOYEE": "ملغى من الموظف",
}

# Leave approval log action types
ACTION_LABELS_AR = {
    "SUBMIT": "تقديم الطلب",
    "UPLOAD_SIGNED_PAPER": "رفع الورقة الموقعة",
    "HR_APPROVE": "اعتماد الموارد البشرية",
    "HR_REJECT": "رفض الموارد البشرية",
    "HR_DIRECT_DECISION": "قرار مباشر من الموارد البشرية",
    "AUTO_REJECT_72H": "رفض آلي بعد 72 ساعة",
    "CANCEL_BY_EMPLOYEE": "إلغاء من الموظف",
}

# Employee assignment action types (EmployeeAssignment.action_type)
ASSIGNMENT_ACTION_LABELS_AR = {
    "INITIAL_ASSIGNMENT": "بدء تكليف",
    "RENEWAL": "تجديد تكليف",
    "ENDED": "إنهاء تكليف",
}

# Leave ledger transaction types
TRANSACTION_LABELS_AR = {
    "ANNUAL_GRANT": "منح سنوي",
    "RESERVE": "حجز",
    "RELEASE": "تحرير حجز",
    "DEDUCT": "خصم",
    "REVERSAL": "عكس حركة",
    "BIOMETRIC_DEDUCT": "خصم من البصمة",
    "HR_ADJUSTMENT": "تسوية من الموارد البشرية",
}

# Leave request entry sources
ENTRY_SOURCE_LABELS_AR = {
    "EMPLOYEE_PORTAL": "بوابة الموظف",
    "HR_DIRECT_DECISION": "قرار مباشر من الموارد البشرية",
}

# Import job statuses
IMPORT_STATUS_LABELS_AR = {
    "PROCESSING": "قيد المعالجة",
    "PREVIEW_READY": "المعاينة جاهزة",
    "COMMITTED": "معتمد ومحفوظ",
    "FAILED": "فشل",
}

# Import error types
IMPORT_ERROR_TYPE_LABELS_AR = {
    "REQUIRED_MISSING": "حقل مطلوب فارغ",
    "UNKNOWN_REFERENCE": "قيمة غير معروفة",
    "INVALID_VALUE": "قيمة غير صالحة",
    "DUPLICATE_IN_DB": "مكرر في النظام",
    "DUPLICATE_IN_FILE": "مكرر في الملف",
    "OUT_OF_SCOPE": "خارج نطاق الصلاحية",
}

from app.services.employee_export import EXPORT_COLUMNS

# Employee change log field names: every employee field uses its Arabic Excel label,
# plus the codes that have no matching Excel column.
CHANGE_FIELD_LABELS_AR: dict[str, str] = {c.key: c.label for c in EXPORT_COLUMNS}
CHANGE_FIELD_LABELS_AR.update(
    {
        "__created__": "إنشاء السجل",
        "account_is_active": "حالة حساب الدخول",
        "employee_code": "كود الموظف",
        "assignment:INITIAL_ASSIGNMENT": "بدء تكليف",
        "assignment:RENEWAL": "تجديد تكليف",
        "assignment:ENDED": "إنهاء تكليف",
        "qualification": "مؤهل علمي",
        "training": "دورة تدريبية",
    }
)

# Validation field labels (for pydantic errors): employee fields from EXPORT_COLUMNS
# plus leave, account and form fields.
FIELD_LABELS_AR: dict[str, str] = {c.key: c.label for c in EXPORT_COLUMNS}
FIELD_LABELS_AR.update(
    {
    # Leave fields:
    "leave_type_code": "نوع الإجازة",
    "start_date": "تاريخ البداية",
    "end_date": "تاريخ النهاية",
    "start_time": "وقت البداية",
    "end_time": "وقت النهاية",
    "reason": "السبب",
    "notes": "الملاحظات",
    "change_reason": "سبب التعديل",
    "hr_decision_number": "رقم القرار",
    "decision_number": "رقم القرار",
    "employee_id": "الموظف",
    "password": "كلمة السر",
    "new_password": "كلمة السر الجديدة",
    "pin": "الرمز السري",
    "otp": "رمز Google Authenticator",
    "year": "السنة",
    "delta_minutes": "قيمة التسوية بالدقائق",
    # Qualifications & trainings:
    "qualification_level": "المؤهل العلمي",
    "specialization": "الاختصاص",
    "issuing_institution": "الجهة المانحة",
    "graduation_year": "سنة التخرج",
    "course_name": "اسم الدورة",
    "training_provider": "الجهة المنظمة",
    "course_date": "تاريخ الدورة",
    "duration_text": "مدة الدورة",
    # Assignment:
    "assigned_position_or_unit": "المنصب أو الوحدة المكلف فيها",
    # Leave forms:
    "page_map": "ربط الصفحات بالأنواع",
    "file": "الملف",
    # Misc:
    "name_ar": "الاسم",
    "date_from": "من تاريخ",
    "date_to": "إلى تاريخ",
    }
)


def label_for(code: str | None, mapping: dict[str, str]) -> str | None:
    """Returns the Arabic label for the code, falling back to the code itself."""
    if code is None:
        return None
    return mapping.get(code, code)
