import re
import unicodedata
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
import csv
import io
from openpyxl import Workbook, load_workbook

EMPTY_TOKENS = {
    "", "-", "--", "—", "nan", "null", "none", "n/a", "na",
    "لا يوجد", "لايوجد", "غير موجود", "غير متوفر",
}
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")
_AR_MARKS = re.compile(r"[\u064B-\u065F\u0670\u0640]")
_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_EXCEL_EPOCH = datetime(1899, 12, 30)
_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y.%m.%d",
)


class RefError(ValueError):
    """قيمة تشير إلى مرجع غير موجود (محافظة أو فئة غير معروفة)."""


def norm_text(value) -> str:
    """توحيد النص العربي للمقارنة: يتجاهل التشكيل والهمزات والرموز والمسافات الزائدة."""
    s = unicodedata.normalize("NFKC", str(value))
    s = _ZERO_WIDTH.sub("", s)
    s = _AR_MARKS.sub("", s).translate(_AR_MAP)
    s = re.sub(r"[\W_]+", " ", s)
    return " ".join(s.split()).lower()


def clean_cell(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = _ZERO_WIDTH.sub("", v).replace("\xa0", " ").strip()
        return None if s.lower() in EMPTY_TOKENS else s
    if isinstance(v, float) and v != v:  # NaN
        return None
    return v


def to_text(v) -> str | None:
    v = clean_cell(v)
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def to_int(v) -> int | None:
    t = to_text(v)
    if t is None:
        return None
    t = t.translate(_DIGITS)
    if not re.fullmatch(r"\d+(\.0+)?", t):
        raise ValueError("يجب أن تكون القيمة رقماً صحيحاً")
    return int(float(t))


def to_date(v) -> date | None:
    v = clean_cell(v)
    if v is None:
        return None
    if isinstance(v, datetime):
        d = v.date()
    elif isinstance(v, date):
        d = v
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        if float(v).is_integer() and 1900 <= v <= 2100:
            raise ValueError("القيمة سنة فقط، اكتب التاريخ كاملاً (يوم/شهر/سنة)")
        if not 1 <= v < 80000:
            raise ValueError("تاريخ غير صالح")
        d = (_EXCEL_EPOCH + timedelta(days=float(v))).date()
    else:
        s = str(v).strip().translate(_DIGITS)
        d = None
        for fmt in _DATE_FORMATS:
            try:
                d = datetime.strptime(s, fmt).date()
                break
            except ValueError:
                continue
        if d is None:
            raise ValueError("صيغة التاريخ غير مفهومة، استخدم يوم/شهر/سنة")
    if not 1900 <= d.year <= 2100:
        raise ValueError("السنة خارج المدى المعقول")
    return d


def to_phone(v) -> str | None:
    t = to_text(v)
    if t is None:
        return None
    digits = re.sub(r"[^\d+]", "", t.translate(_DIGITS))
    if re.fullmatch(r"9\d{8}", digits):  # أضاع Excel الصفر الأول
        digits = "0" + digits
    if not re.fullmatch(r"\+?\d{7,15}", digits):
        raise ValueError("رقم الهاتف غير صالح")
    return digits


def to_national_id(v) -> str | None:
    t = to_text(v)
    if t is None:
        return None
    t = t.replace(" ", "").translate(_DIGITS)
    if not t.isdigit():
        raise ValueError("الرقم الوطني يجب أن يتكون من أرقام فقط")
    return t


def read_sheet(path: Path, sheet_name: str | None, header_row: int, max_rows: int):
    """يرجع (العناوين، [(رقم الصف في Excel، القيم)]) ويتجاهل الصفوف الفارغة تماماً."""
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name:
            if sheet_name not in wb.sheetnames:
                raise ValueError(f"الورقة '{sheet_name}' غير موجودة في الملف")
            ws = wb[sheet_name]
        else:
            ws = wb.worksheets[0]
        ws.reset_dimensions()
        headers = None
        rows = []
        for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if idx < header_row:
                continue
            if idx == header_row:
                headers = [clean_cell(c) for c in row]
                continue
            if all(clean_cell(c) is None for c in row):
                continue
            rows.append((idx, list(row)))
            if len(rows) > max_rows:
                raise ValueError(f"عدد الصفوف يتجاوز الحد المسموح ({max_rows})")
        if headers is None or all(h is None for h in headers):
            raise ValueError("لم أجد صف العناوين، تحقق من رقم صف العناوين")
        return headers, rows
    finally:
        wb.close()


def put_cell(ws, row: int, col: int, value):
    """يكتب خلية ويمنع تفسير النص الذي يبدأ بـ = كصيغة."""
    cell = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str) and value.startswith("="):
        cell.data_type = "s"
    return cell


def workbook_bytes(wb: Workbook) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ======================= CSV =======================
csv.field_size_limit(1_000_000)


def _decode_bytes(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1256"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("ترميز الملف غير مدعوم، احفظه بترميز UTF-8")


def _detect_delimiter(text: str, header_row: int) -> str:
    lines = text.splitlines()
    line = lines[header_row - 1] if 0 < header_row <= len(lines) else ""
    counts = {d: line.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def _unescape_cell(c):
    # يزيل الفاصلة العليا التي يضيفها التصدير لحماية الصيغ
    if isinstance(c, str) and len(c) > 1 and c[0] == "'" and c[1] in "=@+-\t\r":
        return c[1:]
    return c


def read_csv(path: Path, header_row: int, max_rows: int):
    text = _decode_bytes(path.read_bytes())
    reader = csv.reader(
        io.StringIO(text, newline=""), delimiter=_detect_delimiter(text, header_row)
    )
    headers = None
    rows = []
    try:
        for idx, row in enumerate(reader, start=1):
            if idx < header_row:
                continue
            if idx == header_row:
                headers = [clean_cell(c) for c in row]
                continue
            if all(clean_cell(c) is None for c in row):
                continue
            rows.append((idx, [_unescape_cell(c) for c in row]))
            if len(rows) > max_rows:
                raise ValueError(f"عدد الصفوف يتجاوز الحد المسموح ({max_rows})")
    except csv.Error:
        raise ValueError("ملف CSV غير صالح (تنسيق الاقتباس أو الفواصل)")
    if headers is None or all(h is None for h in headers):
        raise ValueError("لم أجد صف العناوين، تحقق من رقم صف العناوين")
    return headers, rows


def read_table(path: Path, sheet_name: str | None, header_row: int, max_rows: int):
    if path.suffix.lower() == ".csv":
        return read_csv(path, header_row, max_rows)
    return read_sheet(path, sheet_name, header_row, max_rows)


def iter_source_rows(path: Path, sheet_name: str | None, header_row: int):
    """يمر على كل صفوف الملف الأصلي (xlsx أو csv) كـ (رقم الصف، القيم)."""
    if path.suffix.lower() == ".csv":
        text = _decode_bytes(path.read_bytes())
        reader = csv.reader(
            io.StringIO(text, newline=""),
            delimiter=_detect_delimiter(text, header_row),
        )
        for idx, row in enumerate(reader, start=1):
            yield idx, list(row)
        return
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet_name] if sheet_name else wb.worksheets[0]
        ws.reset_dimensions()
        for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            yield idx, list(row)
    finally:
        wb.close()