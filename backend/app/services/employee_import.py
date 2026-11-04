import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AppointmentCategory,
    Employee,
    EmployeeQualification,
    EmployeeTraining,
    Governorate,
    OrgUnit,
    User,
)
from app.services.excel_utils import (
    RefError,
    norm_text,
    read_sheet,
    to_date,
    to_int,
    to_national_id,
    to_phone,
    to_text,
    workbook_bytes,
)
from app.services.scope import get_scope

MAX_ROWS = 20_000
INSERT_BATCH = 500

# الحقل -> (النوع، [العناوين المقبولة في Excel، الأول هو عنوان القالب])
COLUMNS: dict[str, tuple[str, list[str]]] = {
    "self_registry_number": ("int", ["الرقم الذاتي في سجلات العاملين", "الرقم الذاتي"]),
    "biometric_code": ("text", ["رقم الموظف في البصمة", "رقم البصمة", "رقم الموظف في منصة البصمة"]),
    "first_name": ("text", ["الاسم"]),
    "father_name": ("text", ["اسم الأب"]),
    "last_name": ("text", ["النسبة"]),
    "full_name_spaced": ("text", ["الاسم الثلاثي"]),
    "mother_full_name": ("text", ["اسم الأم الكامل", "اسم الأم"]),
    "national_id": ("national_id", ["الرقم الوطني"]),
    "gender": ("text", ["الجنس"]),
    "birth_date": ("date", ["تاريخ التولد", "تاريخ الميلاد"]),
    "birth_place": ("text", ["محل الولادة"]),
    "country": ("text", ["الدولة"]),
    "civil_reg_governorate": ("text", ["المحافظة"]),
    "civil_reg_secretariat": ("text", ["الأمانة"]),
    "civil_reg_place": ("text", ["مكان القيد"]),
    "civil_reg_number": ("text", ["رقم القيد"]),
    "marital_status": ("text", ["الوضع العائلي"]),
    "wives_count": ("int", ["عدد الزوجات"]),
    "children_count": ("int", ["عدد الأبناء"]),
    "children_details": ("text", ["الأبناء"]),
    "residence_governorate": ("text", ["السكن الحالي (المحافظة)"]),
    "residence_city_region": ("text", ["السكن الحالي (المنطقة المدينة)"]),
    "residence_address_detail": ("text", ["تفصيل مكان السكن"]),
    "work_governorate": ("governorate", ["محافظة العمل"]),
    "appointment_category": ("category", ["رمز نوع التعيين/التعاقد", "رمز فئة التعيين", "فئة التعيين"]),
    "org_level_1": ("org_level", ["المستوى التنظيمي الأول"]),
    "org_level_2": ("org_level", ["المستوى التنظيمي الثاني"]),
    "org_level_3": ("org_level", ["المستوى التنظيمي الثالث"]),
    "org_level_4": ("org_level", ["المستوى التنظيمي الرابع"]),
    "org_level_5": ("org_level", ["المستوى التنظيمي الخامس"]),
    "job_title_name": ("text", ["مسمى العمل"]),
    "job_classification": ("text", ["التصنيف"]),
    "current_job_category": ("text", ["الفئة الوظيفية الحالية"]),
    "job_rank": ("text", ["المرتبة"]),
    "job_grade": ("text", ["الدرجة"]),
    "permanent_or_contract": ("emp_type", ["مثبت او متعاقد"]),
    "employment_pattern": ("text", ["نمط التعيين أو التعاقد"]),
    "employment_status": ("text", ["الحالة"]),
    "status_details": ("text", ["تفصيل الحالة"]),
    "merger_details": ("text", ["تفاصيل الدمج"]),
    "hiring_qualification": ("qual_hiring", ["آخر مؤهل علمي معيّن على أساسه"]),
    "qualifications_excel_raw": ("text", ["المؤهلات العلمية"]),
    "trainings_raw": ("training_list", ["الدورات التدريبية"]),
    "state_start_date": ("date", ["تاريخ بدء العمل بالدولة"]),
    "hire_date": ("date", ["تاريخ التعيين"]),
    "work_start_date": ("date", ["تاريخ المباشرة"]),
    "ministry_start_date": ("date", ["تاريخ بدء العمل بوزارة التنمية الإدارية"]),
    "termination_date": ("date", ["تاريخ الاستقالة/انهاء العقد", "تاريخ الاستقالة"]),
    "assignment_start_date": ("date", ["تاريخ بدء التكليف"]),
    "assignment_end_date": ("date", ["تاريخ انتهاء التكليف"]),
    "assignment_duration": ("text", ["مدة التكليف"]),
    "assignment_renewal_count": ("int", ["مرات تجديد التكليف", "عدد مرات تجديد التكليف"]),
    "phone_number": ("phone", ["رقم الهاتف"]),
    "electronic_account": ("text", ["حساب الكتروني"]),
    "sham_cash_account": ("text", ["حساب شام كاش"]),
    "addition_request_info": ("text", ["طلب الإضافة"]),
    "central_notes": ("text", ["ملاحظات مركزية"]),
}

LABEL = {f: aliases[0] for f, (_, aliases) in COLUMNS.items()}
ALIAS_INDEX = {norm_text(a): f for f, (_, aliases) in COLUMNS.items() for a in aliases}
IGNORED_HEADERS = {norm_text("العمر"), norm_text("كود الموظف")}  # حقلان مشتقان  # حقل مشتق من تاريخ التولد
FULL_NAME_KEY = norm_text("الاسم الثلاثي")
TEXT_FORMAT_FIELDS = ("national_id", "phone_number", "biometric_code", "civil_reg_number")
NON_EMPLOYEE_KINDS = ("org_level", "governorate", "category", "qual_hiring", "training_list")

INSERT_FIELDS = [
    f for f, (kind, _) in COLUMNS.items() if kind not in NON_EMPLOYEE_KINDS
] + ["governorate_code", "appointment_category_code", "org_levels_import_raw", "org_unit_id"]

INSTRUCTIONS = [
    "تعليمات تعبئة قالب استيراد الموظفين",
    "1) لا تغيّر أسماء الأعمدة في الورقة الأولى، ويمكنك حذف الأعمدة التي لا تحتاجها.",
    "2) الأعمدة الإلزامية: محافظة العمل، رقم الهاتف، تاريخ بدء العمل بالدولة.",
    "3) الاسم والنسبة إلزاميان، أو الاسم الثلاثي إن كان من ثلاث كلمات بالضبط.",
    "4) مثبت او متعاقد: إلزامي إلا إذا ملأت رمز فئة التعيين فيُؤخذ منها.",
    "5) محافظة العمل: اكتب الاسم العربي أو الإنجليزي أو الرمز (مثل دمشق أو DM).",
    "6) رمز فئة التعيين اختياري: Aa أو A أو B أو Bb أو Cc أو C. وإن تركته فارغاً يحددها HR لاحقاً ويولَّد الكود عندها.",
    "7) التواريخ بصيغة يوم/شهر/سنة (مثل 01/03/2015) أو تاريخ Excel عادي. السنة وحدها غير مقبولة.",
    "8) الخلايا الفارغة مسموحة في أي عمود غير إلزامي.",
    "9) الصف المكرر (نفس الرقم الوطني أو رقم البصمة) يُرفض ولا يُدخل مرتين.",
    "10) المؤهلات والدورات: ضع كل مؤهل أو دورة في سطر مستقل داخل الخلية (Alt+Enter) أو افصل بينها بـ ; .",
    "11) المستويات التنظيمية تُربط تلقائياً بالوحدات المنشأة بالاسم نفسه من الأعلى إلى الأدنى، وإلا يُحفظ النص فقط.",
    "12) عمودا العمر والاسم_الثلاثي مشتقان ويُتجاهلان عند الاستيراد.",
]


def build_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "الموظفون"
    ws.sheet_view.rightToLeft = True
    for col, (name, (_, aliases)) in enumerate(COLUMNS.items(), start=1):
        ws.cell(row=1, column=col, value=aliases[0]).font = Font(bold=True)
        if name in TEXT_FORMAT_FIELDS:  # يمنع Excel من إسقاط الصفر الأول
            for r in range(2, 2002):
                ws.cell(row=r, column=col).number_format = "@"
    notes = wb.create_sheet("تعليمات")
    notes.sheet_view.rightToLeft = True
    for i, line in enumerate(INSTRUCTIONS, start=1):
        notes.cell(row=i, column=1, value=line)
    return workbook_bytes(wb)


# ---------------------------------------------------------------- المراجع
@dataclass
class Lookups:
    governorates: dict[str, str]
    category_codes: set[str]
    category_labels: dict[str, str]
    category_types: dict[str, str]
    org_index: dict[tuple[int | None, str], int]


async def load_lookups(db: AsyncSession) -> Lookups:
    govs = (await db.scalars(select(Governorate))).all()
    cats = (await db.scalars(select(AppointmentCategory))).all()
    units = (
        await db.scalars(select(OrgUnit).where(OrgUnit.is_active).order_by(OrgUnit.id))
    ).all()
    gmap: dict[str, str] = {}
    for g in govs:
        for key in (g.governorate_name_ar, g.governorate_name_en, g.governorate_code):
            gmap[norm_text(key)] = g.governorate_code
    org_index: dict[tuple[int | None, str], int] = {}
    for u in units:
        org_index.setdefault((u.parent_id, norm_text(u.name_ar)), u.id)
    return Lookups(
        governorates=gmap,
        category_codes={c.category_code for c in cats},
        category_labels={norm_text(c.category_label_ar): c.category_code for c in cats},
        category_types={c.category_code: c.employment_type for c in cats},
        org_index=org_index,
    )


def link_org_unit(levels: dict[str, str], org_index: dict) -> int | None:
    """يسير من المستوى الأول نزولاً، ويتوقف عند أول مستوى فارغ أو غير مطابق."""
    parent: int | None = None
    unit_id: int | None = None
    for lvl in ("1", "2", "3", "4", "5"):
        name = levels.get(lvl)
        if not name:
            break
        found = org_index.get((parent, norm_text(name)))
        if found is None:
            break
        unit_id = parent = found
    return unit_id


# ---------------------------------------------------------------- مؤهلات ودورات
_SPLIT = re.compile(r"[\r\n;؛|]+")


def split_items(raw: str | None) -> list[str]:
    if not raw:
        return []
    items, seen = [], set()
    for part in _SPLIT.split(raw):
        item = part.strip(" \t-•*·")
        key = norm_text(item)
        if item and key not in seen:
            seen.add(key)
            items.append(item)
    return items


def _qual_row(text_value: str, is_hiring: bool) -> dict:
    return {
        "qualification_level": text_value[:100],
        "notes": text_value if len(text_value) > 100 else None,
        "is_hiring_qualification": is_hiring,
    }


def build_qualifications(raw: str | None, hiring: str | None) -> list[dict]:
    hiring_key = norm_text(hiring) if hiring else None
    rows, hiring_done = [], False
    for item in split_items(raw):
        is_hiring = bool(hiring_key) and not hiring_done and norm_text(item) == hiring_key
        hiring_done = hiring_done or is_hiring
        rows.append(_qual_row(item, is_hiring))
    if hiring and not hiring_done:
        rows.append(_qual_row(hiring.strip(), True))
    return rows


# ---------------------------------------------------------------- تحليل الصفوف
RowError = tuple[str | None, str | None, str, str]  # (العمود، القيمة، النوع، الرسالة)


@dataclass
class RowResult:
    row_no: int
    data: dict
    errors: list[RowError] = field(default_factory=list)


def _raw(v) -> str | None:
    return None if v is None else str(v)[:200]


def _convert(kind: str, raw, lk: Lookups):
    if kind in ("text", "org_level", "qual_hiring", "training_list"):
        return to_text(raw)
    if kind == "int":
        return to_int(raw)
    if kind == "date":
        return to_date(raw)
    if kind == "phone":
        return to_phone(raw)
    if kind == "national_id":
        return to_national_id(raw)
    if kind == "governorate":
        t = to_text(raw)
        if t is None:
            return None
        code = lk.governorates.get(norm_text(t))
        if code is None:
            raise RefError(f"محافظة غير معروفة: {t}")
        return code
    if kind == "category":
        t = to_text(raw)
        if t is None:
            return None
        if t in lk.category_codes:
            return t
        code = lk.category_labels.get(norm_text(t))
        if code is None:
            raise RefError(f"رمز فئة التعيين غير معروف: {t}")
        return code
    if kind == "emp_type":
        t = to_text(raw)
        if t is None:
            return None
        n = norm_text(t)
        if n.startswith("مثبت"):
            return "مثبت"
        if n.startswith("متعاقد") or n.startswith("عقد"):
            return "متعاقد"
        raise ValueError("القيمة يجب أن تكون: مثبت أو متعاقد")
    raise ValueError(f"نوع عمود غير معروف: {kind}")


def build_mapping(headers: list):
    mapping: dict[int, str] = {}
    unmapped: list[str] = []
    seen: set[str] = set()
    for i, h in enumerate(headers):
        if h is None:
            continue
        key = norm_text(h)
        if key in IGNORED_HEADERS:
            continue
        if "_" in str(h) and key == FULL_NAME_KEY:  # الاسم_الثلاثي المشتق، يُتجاهل
            continue
        f = ALIAS_INDEX.get(key)
        if f is None or f in seen:
            unmapped.append(str(h))
            continue
        seen.add(f)
        mapping[i] = f
    present = set(mapping.values())
    missing = [
        LABEL[f] for f in ("work_governorate", "phone_number", "state_start_date")
        if f not in present
    ]
    if not ({"first_name", "last_name"} <= present or "full_name_spaced" in present):
        missing.append("الاسم والنسبة (أو الاسم الثلاثي)")
    return mapping, unmapped, missing


def _finalize(d: dict, levels: dict, lk: Lookups, errs: list, bad: set) -> None:
    def require(src_field: str, key: str) -> None:
        if not d.get(key) and src_field not in bad:
            errs.append((LABEL[src_field], None, "REQUIRED_MISSING", f"{LABEL[src_field]} مطلوب"))

    require("work_governorate", "governorate_code")
    require("phone_number", "phone_number")
    require("state_start_date", "state_start_date")

    first, father, last = d.get("first_name"), d.get("father_name"), d.get("last_name")
    full = d.get("full_name_spaced")
    if not (first and last):
        parts = full.split() if full else []
        if len(parts) == 3:
            first, father, last = first or parts[0], father or parts[1], last or parts[2]
        elif full:
            errs.append(("الاسم الثلاثي", full, "INVALID_VALUE",
                         "تعذّر تقسيم الاسم الثلاثي لأنه ليس من 3 كلمات، املأ الاسم والنسبة"))
        else:
            errs.append(("الاسم / النسبة", None, "REQUIRED_MISSING",
                         "الاسم والنسبة مطلوبان (أو اسم ثلاثي من 3 كلمات)"))
    if first and last:
        d["first_name"], d["father_name"], d["last_name"] = first, father, last
        d["full_name_spaced"] = " ".join(p for p in (first, father, last) if p)

    cat = d.get("appointment_category_code")
    cat_type = lk.category_types.get(cat) if cat else None
    ptype = d.get("permanent_or_contract")
    if ptype and cat_type and ptype != cat_type:
        errs.append((LABEL["permanent_or_contract"], ptype, "INVALID_VALUE",
                     f"تعارض: الفئة {cat} تعني {cat_type} بينما الخلية تقول {ptype}"))
    elif not ptype:
        if cat_type:
            d["permanent_or_contract"] = cat_type
        elif "permanent_or_contract" not in bad and "appointment_category" not in bad:
            errs.append((LABEL["permanent_or_contract"], None, "REQUIRED_MISSING",
                         "حدد مثبت/متعاقد أو رمز فئة تعيين"))
    d["org_levels_import_raw"] = levels
    d["org_unit_id"] = link_org_unit(levels, lk.org_index) if levels else None


def parse_rows(rows, headers, mapping, lk: Lookups) -> list[RowResult]:
    results: list[RowResult] = []
    for row_no, cells in rows:
        d: dict = {}
        errs: list[RowError] = []
        bad: set[str] = set()
        levels: dict[str, str] = {}
        for idx, f in mapping.items():
            raw = cells[idx] if idx < len(cells) else None
            kind = COLUMNS[f][0]
            label = str(headers[idx])
            try:
                val = _convert(kind, raw, lk)
            except RefError as exc:
                errs.append((label, _raw(raw), "UNKNOWN_REFERENCE", str(exc)))
                bad.add(f)
                continue
            except ValueError as exc:
                errs.append((label, _raw(raw), "INVALID_VALUE", str(exc)))
                bad.add(f)
                continue
            if val is None:
                continue
            if kind == "org_level":
                levels[f[-1]] = val
            elif kind == "governorate":
                d["governorate_code"] = val
            elif kind == "category":
                d["appointment_category_code"] = val
            else:
                d[f] = val
        _finalize(d, levels, lk, errs, bad)
        results.append(RowResult(row_no, d, errs))
    return results


# ---------------------------------------------------------------- التحليل الكامل
@dataclass
class Analysis:
    mapping_info: dict
    file_failed: bool = False
    total_rows: int = 0
    valid: list[tuple[int, dict]] = field(default_factory=list)
    errors: list[tuple[int, str | None, str | None, str, str]] = field(default_factory=list)
    error_rows: int = 0
    duplicate_rows: int = 0


async def _existing(db: AsyncSession, column, values: set[str]) -> set[str]:
    found: set[str] = set()
    vals = list(values)
    for i in range(0, len(vals), 1000):
        rows = await db.scalars(select(column).where(column.in_(vals[i:i + 1000])))
        found.update(rows.all())
    return found


async def analyze(
    db: AsyncSession, path: Path, sheet_name: str | None, header_row: int, actor: User
) -> Analysis:
    try:
        headers, rows = await asyncio.to_thread(
            read_sheet, path, sheet_name, header_row, MAX_ROWS
        )
    except ValueError as exc:
        return Analysis({"file_error": str(exc)}, file_failed=True)
    except Exception:
        return Analysis(
            {"file_error": "تعذّرت قراءة الملف، تأكد أنه بصيغة xlsx وغير تالف"},
            file_failed=True,
        )

    mapping, unmapped, missing = build_mapping(headers)
    info = {
        "mapped": {str(headers[i]): f for i, f in mapping.items()},
        "unmapped": unmapped,
        "missing_required": missing,
        "header_row": header_row,
    }
    if missing:
        return Analysis(info, file_failed=True, total_rows=len(rows))

    lk = await load_lookups(db)
    parsed = await asyncio.to_thread(parse_rows, rows, headers, mapping, lk)
    scope = await get_scope(db, actor)
    info["org_unlinked_rows"] = sum(
        1 for p in parsed
        if p.data.get("org_levels_import_raw") and not p.data.get("org_unit_id")
    )

    nat = {p.data["national_id"] for p in parsed if p.data.get("national_id")}
    bio = {p.data["biometric_code"] for p in parsed if p.data.get("biometric_code")}
    existing = {
        "national_id": await _existing(db, Employee.national_id, nat),
        "biometric_code": await _existing(db, Employee.biometric_code, bio),
    }
    seen: dict[str, dict[str, int]] = {"national_id": {}, "biometric_code": {}}
    labels = {"national_id": "الرقم الوطني", "biometric_code": "رقم البصمة"}

    out = Analysis(info, total_rows=len(rows))
    for p in parsed:
        errs = list(p.errors)
        d = p.data
        is_dup = False
        gov = d.get("governorate_code")
        if scope is not None and gov and not scope.allows(gov, d.get("org_unit_id")):
            errs.append(("محافظة العمل", gov, "OUT_OF_SCOPE", "الموظف خارج نطاق صلاحيتك"))
        for key in ("national_id", "biometric_code"):
            v = d.get(key)
            if not v:
                continue
            if v in existing[key]:
                errs.append((labels[key], v, "DUPLICATE_IN_DB", f"{labels[key]} مسجل مسبقاً في النظام"))
                is_dup = True
            elif v in seen[key]:
                errs.append((labels[key], v, "DUPLICATE_IN_FILE",
                             f"{labels[key]} مكرر في الملف (أول ظهور في الصف {seen[key][v]})"))
                is_dup = True
            else:
                seen[key][v] = p.row_no
        if errs:
            out.error_rows += 1
            out.duplicate_rows += 1 if is_dup else 0
            out.errors.extend((p.row_no, c, raw, t, m) for (c, raw, t, m) in errs)
        else:
            out.valid.append((p.row_no, d))
    return out


async def insert_valid(db: AsyncSession, valid: list[tuple[int, dict]], actor_id: int) -> None:
    n = len(valid)
    serials = (
        await db.scalars(
            text("select nextval('employee_global_serial_seq') from generate_series(1, :n)"),
            {"n": n},
        )
    ).all()
    records = []
    for (_, d), serial in zip(valid, serials):
        formatted = f"{serial:04d}"
        cat = d.get("appointment_category_code")
        rec = {f: d.get(f) for f in INSERT_FIELDS}
        rec.update(
            global_serial_number=serial,
            formatted_serial=formatted,
            employee_code=f"{d['governorate_code']}-{cat}-{formatted}" if cat else None,
            updated_by_hr_id=actor_id,
            org_levels_import_raw=d.get("org_levels_import_raw") or {},
        )
        for f in ("wives_count", "children_count", "assignment_renewal_count"):
            rec[f] = rec[f] or 0
        records.append(rec)

    id_by_serial: dict[int, int] = {}
    for i in range(0, n, INSERT_BATCH):
        result = await db.execute(
            insert(Employee).returning(Employee.id, Employee.global_serial_number),
            records[i:i + INSERT_BATCH],
        )
        for emp_id, serial in result.all():
            id_by_serial[serial] = emp_id

    quals: list[dict] = []
    trainings: list[dict] = []
    for (_, d), serial in zip(valid, serials):
        emp_id = id_by_serial[serial]
        for q in build_qualifications(
            d.get("qualifications_excel_raw"), d.get("hiring_qualification")
        ):
            quals.append({"employee_id": emp_id, "created_by_user_id": actor_id, **q})
        for t in split_items(d.get("trainings_raw")):
            trainings.append(
                {
                    "employee_id": emp_id,
                    "course_name": t[:200],
                    "notes": t if len(t) > 200 else None,
                    "created_by_user_id": actor_id,
                }
            )
    for i in range(0, len(quals), INSERT_BATCH):
        await db.execute(insert(EmployeeQualification), quals[i:i + INSERT_BATCH])
    for i in range(0, len(trainings), INSERT_BATCH):
        await db.execute(insert(EmployeeTraining), trainings[i:i + INSERT_BATCH])