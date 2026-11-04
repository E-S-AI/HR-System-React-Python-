import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Employee,
    EmployeeQualification,
    EmployeeTraining,
    ExportLog,
    Governorate,
    OrgUnit,
    User,
)
from app.schemas.exports import EmployeeExportFilters
from app.services.excel_utils import workbook_bytes
from app.services.scope import descendant_ids, get_scope
import csv
import io

BATCH = 2000
MAX_EXPORT_ROWS = 50_000
_slots = asyncio.Semaphore(2)  # تصديران متزامنان كحد أقصى لحماية الذاكرة
_BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass(frozen=True)
class ExportColumn:
    key: str
    label: str
    default: bool = True


# الأعمدة الـ 56 بالأسماء والترتيب المعتمدين، ثم أعمدة إضافية اختيارية
EXPORT_COLUMNS: list[ExportColumn] = [
    ExportColumn("self_registry_number", "الرقم الذاتي في سجلات العاملين"),
    ExportColumn("first_name", "الاسم"),
    ExportColumn("father_name", "اسم الأب"),
    ExportColumn("last_name", "النسبة"),
    ExportColumn("full_name_spaced", "الاسم الثلاثي"),
    ExportColumn("full_name_underscored", "الاسم_الثلاثي"),
    ExportColumn("mother_full_name", "اسم الأم الكامل"),
    ExportColumn("national_id", "الرقم الوطني"),
    ExportColumn("gender", "الجنس"),
    ExportColumn("birth_date", "تاريخ التولد"),
    ExportColumn("age", "العمر"),
    ExportColumn("birth_place", "محل الولادة"),
    ExportColumn("country", "الدولة"),
    ExportColumn("civil_reg_governorate", "المحافظة"),
    ExportColumn("civil_reg_secretariat", "الأمانة"),
    ExportColumn("civil_reg_place", "مكان القيد"),
    ExportColumn("civil_reg_number", "رقم القيد"),
    ExportColumn("marital_status", "الوضع العائلي"),
    ExportColumn("wives_count", "عدد الزوجات"),
    ExportColumn("children_count", "عدد الأبناء"),
    ExportColumn("children_details", "الأبناء"),
    ExportColumn("residence_governorate", "السكن_الحالي _( المحافظة )"),
    ExportColumn("residence_city_region", "السكن_الحالي_(المنطقة_المدينة )"),
    ExportColumn("residence_address_detail", "تفصيل مكان السكن"),
    ExportColumn("work_governorate", "محافظة العمل"),
    ExportColumn("org_level_1", "المستوى التنظيمي الأول"),
    ExportColumn("org_level_2", "المستوى التنظيمي الثاني"),
    ExportColumn("org_level_3", "المستوى التنظيمي الثالث"),
    ExportColumn("org_level_4", "المستوى التنظيمي الرابع"),
    ExportColumn("org_level_5", "المستوى التنظيمي الخامس"),
    ExportColumn("job_title_name", "مسمى العمل"),
    ExportColumn("job_classification", "التصنيف"),
    ExportColumn("current_job_category", "الفئة الوظيفية الحالية"),
    ExportColumn("job_rank", "المرتبة"),
    ExportColumn("job_grade", "الدرجة"),
    ExportColumn("permanent_or_contract", "مثبت او متعاقد"),
    ExportColumn("employment_pattern", "نمط التعيين أو التعاقد"),
    ExportColumn("employment_status", "الحالة"),
    ExportColumn("status_details", "تفصيل الحالة"),
    ExportColumn("merger_details", "تفاصيل الدمج"),
    ExportColumn("hiring_qualification", "آخر مؤهل علمي معيّن على أساسه"),
    ExportColumn("qualifications", "المؤهلات العلمية"),
    ExportColumn("trainings", "الدورات التدريبية"),
    ExportColumn("state_start_date", "تاريخ بدء العمل بالدولة"),
    ExportColumn("hire_date", "تاريخ التعيين"),
    ExportColumn("work_start_date", "تاريخ المباشرة"),
    ExportColumn("ministry_start_date", "تاريخ بدء العمل بوزارة التنمية الإدارية"),
    ExportColumn("termination_date", "تاريخ الاستقالة/انهاء العقد"),
    ExportColumn("assignment_start_date", "تاريخ بدء التكليف"),
    ExportColumn("assignment_end_date", "تاريخ انتهاء التكليف"),
    ExportColumn("assignment_duration", "مدة التكليف"),
    ExportColumn("phone_number", "رقم الهاتف"),
    ExportColumn("electronic_account", "حساب الكتروني"),
    ExportColumn("sham_cash_account", "حساب شام كاش"),
    ExportColumn("addition_request_info", "طلب الإضافة"),
    ExportColumn("central_notes", "ملاحظات مركزية"),
    # --- إضافية (غير مضمنة افتراضياً) ---
    ExportColumn("employee_code", "كود الموظف", default=False),
    ExportColumn("biometric_code", "رقم الموظف في البصمة", default=False),
    ExportColumn("appointment_category_code", "رمز نوع التعيين/التعاقد", default=False),
    ExportColumn("assignment_renewal_count", "مرات تجديد التكليف", default=False),
]
COLUMN_BY_KEY = {c.key: c for c in EXPORT_COLUMNS}


def resolve_columns(keys: list[str] | None) -> list[ExportColumn]:
    if not keys:
        return [c for c in EXPORT_COLUMNS if c.default]
    unknown = [k for k in keys if k not in COLUMN_BY_KEY]
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"أعمدة غير معروفة: {', '.join(unknown)}"
        )
    seen: set[str] = set()
    out = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(COLUMN_BY_KEY[k])
    return out


# ---------------------------------------------------------------- الفلاتر
async def build_conditions(db: AsyncSession, actor: User, f: EmployeeExportFilters):
    conds = []
    scope = await get_scope(db, actor)
    if scope is not None:
        conds.append(scope.employee_filter())
    if f.governorate_code:
        conds.append(Employee.governorate_code == f.governorate_code)
    if f.org_unit_id is not None:
        ids = (
            await descendant_ids(db, {f.org_unit_id})
            if f.include_sub_units
            else {f.org_unit_id}
        )
        conds.append(Employee.org_unit_id.in_(list(ids)))
    if f.permanent_or_contract:
        conds.append(Employee.permanent_or_contract == f.permanent_or_contract)
    if f.appointment_category_code:
        conds.append(Employee.appointment_category_code == f.appointment_category_code)
    if f.employment_status:
        conds.append(Employee.employment_status == f.employment_status)
    if f.has_account is not None:
        account = exists().where(User.employee_id == Employee.id)
        conds.append(account if f.has_account else ~account)
    if f.state_start_from:
        conds.append(Employee.state_start_date >= f.state_start_from)
    if f.state_start_to:
        conds.append(Employee.state_start_date <= f.state_start_to)
    if f.search:
        esc = f.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pat = f"%{esc}%"
        conds.append(
            or_(
                Employee.full_name_spaced.ilike(pat, escape="\\"),
                Employee.national_id.ilike(pat, escape="\\"),
                Employee.employee_code.ilike(pat, escape="\\"),
                Employee.phone_number.ilike(pat, escape="\\"),
            )
        )
    return conds


# ---------------------------------------------------------------- حساب القيم
@dataclass
class Ctx:
    gov_names: dict[str, str]
    units: dict[int, tuple[str, int | None]]
    today: date = field(default_factory=date.today)
    _paths: dict[int, list[str]] = field(default_factory=dict)

    def path(self, unit_id: int) -> list[str]:
        cached = self._paths.get(unit_id)
        if cached is not None:
            return cached
        names, cur = [], unit_id
        while cur is not None and cur in self.units and len(names) < 6:
            name, parent = self.units[cur]
            names.append(name)
            cur = parent
        names.reverse()
        self._paths[unit_id] = names
        return names

    def org_level(self, row, level: int) -> str | None:
        uid = row["org_unit_id"]
        if uid is not None and uid in self.units:
            names = self.path(uid)
            return names[level - 1] if level - 1 < len(names) else None
        raw = row["org_levels_import_raw"] or {}
        return raw.get(str(level))


async def load_ctx(db: AsyncSession) -> Ctx:
    govs = (await db.execute(select(Governorate.governorate_code, Governorate.governorate_name_ar))).all()
    units = (await db.execute(select(OrgUnit.id, OrgUnit.name_ar, OrgUnit.parent_id))).all()
    return Ctx(
        gov_names={code: name for code, name in govs},
        units={uid: (name, parent) for uid, name, parent in units},
    )


def _item_text(name: str, notes: str | None) -> str:
    # الاستيراد يحفظ النص الكامل في notes إن زاد عن حد العمود
    return notes if notes and notes.startswith(name) else name


async def load_extras(db: AsyncSession, ids: list[int], need_q: bool, need_t: bool):
    quals: dict[int, list[tuple[str, bool]]] = defaultdict(list)
    trains: dict[int, list[str]] = defaultdict(list)
    if need_q:
        rows = await db.execute(
            select(
                EmployeeQualification.employee_id,
                EmployeeQualification.qualification_level,
                EmployeeQualification.notes,
                EmployeeQualification.is_hiring_qualification,
            )
            .where(EmployeeQualification.employee_id.in_(ids))
            .order_by(EmployeeQualification.id)
        )
        for emp_id, level, notes, hiring in rows.all():
            quals[emp_id].append((_item_text(level, notes), hiring))
    if need_t:
        rows = await db.execute(
            select(
                EmployeeTraining.employee_id,
                EmployeeTraining.course_name,
                EmployeeTraining.notes,
            )
            .where(EmployeeTraining.employee_id.in_(ids))
            .order_by(EmployeeTraining.id)
        )
        for emp_id, name, notes in rows.all():
            trains[emp_id].append(_item_text(name, notes))
    return quals, trains


def compute(key: str, row, ctx: Ctx, quals, trains):
    if key == "full_name_underscored":
        name = row["full_name_spaced"]
        return "_".join(name.split()) if name else None
    if key == "age":
        bd = row["birth_date"]
        if bd is None:
            return None
        t = ctx.today
        return t.year - bd.year - ((t.month, t.day) < (bd.month, bd.day))
    if key == "work_governorate":
        code = row["governorate_code"]
        return ctx.gov_names.get(code, code)
    if key.startswith("org_level_"):
        return ctx.org_level(row, int(key[-1]))
    if key == "hiring_qualification":
        for text_value, hiring in quals or []:
            if hiring:
                return text_value
        return None
    if key == "qualifications":
        if quals:
            return "\n".join(t for t, _ in quals)
        return row["qualifications_excel_raw"]
    if key == "trainings":
        return "\n".join(trains) if trains else None
    return row[key]


async def fetch_rows(db: AsyncSession, conds, columns: list[ExportColumn], ctx: Ctx):
    keys = {c.key for c in columns}
    need_q = bool(keys & {"hiring_qualification", "qualifications"})
    need_t = "trainings" in keys
    table = Employee.__table__
    out: list[list] = []
    last_id = 0
    while True:
        rows = (
            await db.execute(
                select(table)
                .where(table.c.id > last_id, *conds)
                .order_by(table.c.id)
                .limit(BATCH)
            )
        ).mappings().all()
        if not rows:
            break
        last_id = rows[-1]["id"]
        ids = [r["id"] for r in rows]
        quals, trains = await load_extras(db, ids, need_q, need_t)
        for r in rows:
            out.append(
                [
                    compute(c.key, r, ctx, quals.get(r["id"]), trains.get(r["id"]))
                    for c in columns
                ]
            )
        if len(rows) < BATCH:
            break
    return out


# ---------------------------------------------------------------- بناء الملف
def _safe(ws, v):
    if isinstance(v, str):
        v = _BAD_XML.sub("", v)[:32000]
        if v.startswith("="):  # منع تفسير النص كصيغة Excel
            cell = WriteOnlyCell(ws, value=v)
            cell.data_type = "s"
            return cell
    return v


def build_workbook(columns: list[ExportColumn], rows: list[list]) -> bytes:
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("الموظفون")
    ws.sheet_view.rightToLeft = True
    ws.freeze_panes = "A2"
    for i in range(1, len(columns) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 20
    header = []
    for c in columns:
        cell = WriteOnlyCell(ws, value=c.label)
        cell.font = Font(bold=True)
        header.append(cell)
    ws.append(header)
    for row in rows:
        ws.append([_safe(ws, v) for v in row])
    return workbook_bytes(wb)

_NUMERIC_LIKE = re.compile(r"^[+-]?[\d\s().\-]+$")


def _csv_cell(v):
    if isinstance(v, str):
        v = _BAD_XML.sub("", v)
        if v and (v[0] in "=@\t\r" or (v[0] in "+-" and not _NUMERIC_LIKE.match(v))):
            return "'" + v  # يمنع تفسيرها كصيغة عند فتح الملف في Excel
    return v


def build_csv(columns: list[ExportColumn], rows: list[list], delimiter: str = ",") -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\r\n")
    writer.writerow([c.label for c in columns])
    for row in rows:
        writer.writerow([_csv_cell(v) for v in row])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


async def export_employees(
    db: AsyncSession,
    actor: User,
    filters: EmployeeExportFilters,
    column_keys: list[str] | None,
    file_format: str = "xlsx",
    delimiter: str = ",",
) -> bytes:
    columns = resolve_columns(column_keys)
    conds = await build_conditions(db, actor, filters)
    total = await db.scalar(select(func.count()).select_from(Employee).where(*conds))
    if total > MAX_EXPORT_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"عدد الصفوف ({total}) يتجاوز الحد المسموح ({MAX_EXPORT_ROWS}). ضيّق الفلاتر وصدّر على دفعات",
        )
    async with _slots:
        ctx = await load_ctx(db)
        rows = await fetch_rows(db, conds, columns, ctx)
        if file_format == "csv":
            data = await asyncio.to_thread(build_csv, columns, rows, delimiter)
        else:
            data = await asyncio.to_thread(build_workbook, columns, rows)

    db.add(
        ExportLog(
            exported_by_user_id=actor.id,
            module_name="EMPLOYEES",
            applied_filters={
                **filters.model_dump(mode="json", exclude_none=True),
                "file_format": file_format,
            },
            selected_columns=[c.key for c in columns],
            exported_rows_count=len(rows),
        )
    )
    await db.commit()
    return data


def export_filename(ext: str = "xlsx") -> str:
    return f"employees_{datetime.now():%Y%m%d_%H%M}.{ext}"