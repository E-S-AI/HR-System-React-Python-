"""نماذج الإجازات الورقية الجاهزة (PDF مرفوع من الموارد البشرية).

الملف الأصلي يحوي عدة صفحات (صفحة لكل نوع)، فيُقسَّم إلى ملفات صفحة واحدة
ويُحفظ مسار كل منها (نسبياً إلى upload_dir) في leave_types.printable_pdf_template_path.
"""

import asyncio
import io
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import LeaveType
from app.schemas.leave_form import LeaveFormRead, LeaveFormUploadItem

logger = logging.getLogger(__name__)

MAX_TEMPLATE_BYTES = 10 * 1024 * 1024
MAX_PAGES = 50
TEMPLATES_SUBDIR = "leave_forms/templates"
_ENTRY_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=([0-9]+)$")


def _bad(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


# ------------------------------------------------------------------ المسارات
def _base() -> Path:
    return Path(settings.upload_dir).resolve()


def template_abs(rel: str) -> Path:
    """يحوّل المسار النسبي إلى مطلق ويرفض أي مسار يخرج عن upload_dir."""
    base = _base()
    path = (base / rel).resolve()
    if base not in path.parents:
        raise _bad(404, "الملف غير موجود")
    return path


def _rel(path: Path) -> str:
    return path.relative_to(_base()).as_posix()


def _mtime_utc(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _safe_path(rel: str | None) -> Path | None:
    if not rel:
        return None
    try:
        return template_abs(rel)
    except HTTPException:
        logger.warning("template path outside upload_dir ignored: %s", rel)
        return None


# ------------------------------------------------------------------ التحقق
def parse_page_map(text: str | None) -> dict[str, int]:
    if text is None or not text.strip():
        raise _bad(422, "حقل page_map مطلوب، مثال: HOURLY=1,ADMIN=2,MISSION=3,UNPAID=4")
    result: dict[str, int] = {}
    for raw in text.split(","):
        entry = re.sub(r"\s+", "", raw)
        if not entry:
            raise _bad(422, "صيغة page_map غير صحيحة: يوجد عنصر فارغ")
        m = _ENTRY_RE.match(entry)
        if m is None:
            raise _bad(
                422,
                f"صيغة page_map غير صحيحة عند «{raw.strip()}»، "
                "يجب أن تكون CODE=PAGE برمز إنكليزي كبير ورقم صفحة",
            )
        code, page = m.group(1), int(m.group(2))
        if code in result:
            raise _bad(422, f"الرمز {code} مكرر في page_map")
        result[code] = page
    return result


def _read_pdf(content: bytes) -> int:
    """يتحقق من الملف ويعيد عدد صفحاته."""
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise _bad(422, "ملف PDF محمي بكلمة مرور أو مشفّر، ارفع نسخة غير محمية")
        return len(reader.pages)
    except HTTPException:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        logger.info("invalid template pdf: %s", exc)
        raise _bad(422, "تعذّرت قراءة ملف PDF، الملف تالف أو غير صالح")


def _split_pages(content: bytes, page_map: dict[str, int]) -> dict[str, bytes]:
    reader = PdfReader(io.BytesIO(content))
    out: dict[str, bytes] = {}
    for code, page in page_map.items():
        writer = PdfWriter()
        writer.add_page(reader.pages[page - 1])
        buf = io.BytesIO()
        writer.write(buf)
        out[code] = buf.getvalue()
    return out


def _write_files(files: list[tuple[Path, bytes]], written: list[Path]) -> None:
    for path, data in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(path)


def _unlink_all(paths: list[Path]) -> None:
    for p in paths:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            logger.warning("could not delete template file %s", p)


# ------------------------------------------------------------------ الرفع
async def upload_templates(
    db: AsyncSession, content: bytes, page_map_text: str | None
) -> list[LeaveFormUploadItem]:
    if not content:
        raise _bad(422, "الملف فارغ")
    if len(content) > MAX_TEMPLATE_BYTES:
        raise _bad(413, "حجم الملف يتجاوز 10 ميغابايت")
    if not content.startswith(b"%PDF-"):
        raise _bad(422, "الملف يجب أن يكون بصيغة PDF")

    page_map = parse_page_map(page_map_text)
    page_count = await asyncio.to_thread(_read_pdf, content)
    if not 1 <= page_count <= MAX_PAGES:
        raise _bad(422, f"عدد صفحات الملف يجب أن يكون بين 1 و {MAX_PAGES}")
    for code, page in page_map.items():
        if not 1 <= page <= page_count:
            raise _bad(
                422, f"رقم الصفحة {page} للرمز {code} خارج النطاق (الملف فيه {page_count} صفحة)"
            )

    types = {
        lt.code: lt
        for lt in (
            await db.scalars(
                select(LeaveType).where(LeaveType.code.in_(page_map), LeaveType.is_active)
            )
        ).all()
    }
    missing = [c for c in page_map if c not in types]
    if missing:
        raise _bad(422, f"أنواع إجازات غير موجودة أو غير فعّالة: {', '.join(missing)}")

    try:
        pages = await asyncio.to_thread(_split_pages, content, page_map)
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        logger.info("could not split template pdf: %s", exc)
        raise _bad(422, "تعذّر استخراج صفحات ملف PDF، الملف تالف أو غير صالح")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    targets = {
        code: template_abs(f"{TEMPLATES_SUBDIR}/{code}_{stamp}.pdf") for code in page_map
    }
    if any(await asyncio.to_thread(lambda: [p.exists() for p in targets.values()])):
        raise _bad(409, "تم رفع نماذج قبل لحظات، انتظر ثانية ثم أعد المحاولة")
    written: list[Path] = []
    old_files: list[Path] = []
    try:
        await asyncio.to_thread(
            _write_files, [(targets[c], pages[c]) for c in page_map], written
        )
        locked = {
            lt.code: lt
            for lt in (
                await db.scalars(
                    select(LeaveType)
                    .where(LeaveType.code.in_(page_map))
                    .order_by(LeaveType.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        }
        for code in page_map:
            lt = locked.get(code)
            if lt is None or not lt.is_active:
                raise _bad(409, f"تغيّرت حالة نوع الإجازة {code} أثناء الرفع، أعد المحاولة")
            new_rel = _rel(targets[code])
            old = _safe_path(lt.printable_pdf_template_path)
            if old is not None and old != targets[code]:
                old_files.append(old)
            lt.printable_pdf_template_path = new_rel
        await db.commit()
    except BaseException:
        await db.rollback()
        await asyncio.to_thread(_unlink_all, written)
        raise

    if old_files:
        await asyncio.to_thread(_unlink_all, old_files)

    return [
        LeaveFormUploadItem(
            leave_type_code=code,
            name_ar=types[code].name_ar,
            page=page,
            filename=targets[code].name,
        )
        for code, page in page_map.items()
    ]


# ------------------------------------------------------------------ القراءة والحذف
def _list_status(rows: list[tuple[str, str, bool, str | None]]) -> list[LeaveFormRead]:
    out = []
    for code, name_ar, allow, rel in rows:
        path = _safe_path(rel)
        mtime = _mtime_utc(path) if path is not None and path.is_file() else None
        out.append(
            LeaveFormRead(
                code=code,
                name_ar=name_ar,
                allow_employee_request=allow,
                has_template=mtime is not None,
                updated_at=mtime,
            )
        )
    return out


async def list_templates(db: AsyncSession) -> list[LeaveFormRead]:
    rows = (
        await db.execute(
            select(
                LeaveType.code,
                LeaveType.name_ar,
                LeaveType.allow_employee_request,
                LeaveType.printable_pdf_template_path,
            )
            .where(LeaveType.is_active)
            .order_by(LeaveType.id)
        )
    ).all()
    return await asyncio.to_thread(_list_status, [tuple(r) for r in rows])


async def get_template_path(db: AsyncSession, code: str) -> Path:
    lt = await db.scalar(
        select(LeaveType).where(LeaveType.code == code.upper(), LeaveType.is_active)
    )
    if lt is None:
        raise _bad(404, "نوع الإجازة غير موجود")
    if not lt.printable_pdf_template_path:
        raise _bad(404, "لا يوجد نموذج ورقي مرفوع لهذا النوع من الإجازات")
    path = _safe_path(lt.printable_pdf_template_path)
    if path is None or not await asyncio.to_thread(path.is_file):
        logger.warning(
            "leave form template missing on disk for %s: %s",
            lt.code, lt.printable_pdf_template_path,
        )
        raise _bad(
            404,
            "ملف النموذج غير موجود على الخادم، يرجى من الموارد البشرية إعادة رفع النماذج",
        )
    return path


async def delete_template(db: AsyncSession, code: str) -> None:
    lt = await db.scalar(
        select(LeaveType).where(LeaveType.code == code.upper()).with_for_update()
    )
    if lt is None or not lt.printable_pdf_template_path:
        raise _bad(404, "لا يوجد نموذج ورقي مرفوع لهذا النوع من الإجازات")
    old = _safe_path(lt.printable_pdf_template_path)
    lt.printable_pdf_template_path = None
    await db.commit()
    if old is not None:
        await asyncio.to_thread(_unlink_all, [old])
