"""
Exception handlers for FastAPI, returning Arabic user-facing error messages.
"""
import logging
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError, HTTPException
from app.core.labels_ar import FIELD_LABELS_AR

logger = logging.getLogger(__name__)

# Framework default messages that we translate
_DEFAULT_TRANSLATIONS = {
    "Not Found": "المسار غير موجود",
    "Method Not Allowed": "الطريقة غير مسموحة لهذا المسار",
    "Not authenticated": "يجب تسجيل الدخول",
    "Forbidden": "لا تملك صلاحية لهذه العملية",
    "Unauthorized": "يجب تسجيل الدخول",
}


def _is_default_english(text):
    """Check if the detail is an untranslated default message."""
    if not text or not isinstance(text, str):
        return False
    return text in _DEFAULT_TRANSLATIONS or text.startswith("<!doctype html>")


def http_exception_handler(request: Request, exc: HTTPException):
    """Translates framework defaults; leaves user-raised Arabic messages untouched."""
    detail = exc.detail
    if _is_default_english(detail):
        detail = _DEFAULT_TRANSLATIONS.get(detail, "تعذّر تنفيذ الطلب")
    return JSONResponse({"detail": detail}, status_code=exc.status_code)


def starlette_exception_handler(request: Request, exc: StarletteHTTPException):
    """Same translation logic for Starlette's base exception."""
    detail = exc.detail
    if _is_default_english(detail):
        detail = _DEFAULT_TRANSLATIONS.get(detail, "تعذّر تنفيذ الطلب")
    return JSONResponse({"detail": detail}, status_code=exc.status_code)


def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Returns 422 with Arabic field names and messages.
    {
      "detail": "summary message",
      "errors": [{"field": "name", "label": "الاسم", "message": "الحقل «الاسم» مطلوب"}]
    }
    Never return the raw pydantic errors (ctx contains non-serializable objects).
    """
    errors_out = []
    for err_dict in exc.errors():
        error_type = err_dict["type"]
        loc = err_dict["loc"]
        ctx = err_dict.get("ctx", {})

        # Extract field name: last string element of loc
        field_name = None
        for item in reversed(loc):
            if isinstance(item, str):
                field_name = item
                break
        if field_name is None:
            field_name = "unknown"

        # For list items, append " (السطر N)"
        index_part = ""
        if loc and isinstance(loc[-1], int):
            index_part = f" (السطر {loc[-1] + 1})"

        # Get Arabic label
        label = FIELD_LABELS_AR.get(field_name, field_name)
        label_with_index = label + index_part

        # Build Arabic message
        msg = _error_message(error_type, label_with_index, err_dict.get("msg", ""), ctx)

        errors_out.append({
            "field": field_name + index_part,
            "label": label_with_index,
            "message": msg
        })

    summary = " | ".join(e["message"] for e in errors_out)
    return JSONResponse(
        {"detail": summary, "errors": errors_out},
        status_code=422
    )


def _error_message(error_type: str, label: str, raw_msg: str, ctx: dict) -> str:
    """
    Build an Arabic message for the pydantic error type.
    For value_error (our own validators): strip "Value error, " and keep the rest (already Arabic).
    """
    if error_type == "missing":
        return f"الحقل «{label}» مطلوب"

    if error_type in ("string_type", "int_type", "bool_type", "date_type", "time_type"):
        return f"نوع القيمة في الحقل «{label}» غير صحيح"

    if error_type == "string_too_long":
        max_len = ctx.get("max_length", "")
        return f"الحقل «{label}» أطول من {max_len} حرفاً"

    if error_type == "string_too_short":
        return f"الحقل «{label}» أقصر من المسموح"

    if error_type == "string_pattern_mismatch":
        return f"صيغة الحقل «{label}» غير صحيحة"

    if error_type in ("int_parsing", "float_parsing"):
        return f"الحقل «{label}» يجب أن يكون رقماً"

    if error_type in ("greater_than", "greater_than_equal", "less_than", "less_than_equal"):
        return f"قيمة الحقل «{label}» خارج المدى المسموح"

    if error_type in ("date_parsing", "date_from_datetime_parsing"):
        return f"التاريخ في الحقل «{label}» غير صالح، استخدم الصيغة سنة-شهر-يوم (مثال 2026-12-31)"

    if error_type == "time_parsing":
        return f"الوقت في الحقل «{label}» غير صالح، استخدم الصيغة ساعة:دقيقة (مثال 08:30)"

    if error_type == "datetime_parsing":
        return f"التاريخ والوقت في الحقل «{label}» غير صالحين"

    if error_type == "bool_parsing":
        return f"الحقل «{label}» يجب أن يكون نعم أو لا"

    if error_type in ("literal_error", "enum"):
        return f"قيمة غير مسموحة في الحقل «{label}»"

    if error_type == "extra_forbidden":
        return f"الحقل «{label}» غير معروف أو غير مسموح تعديله"

    if error_type == "too_long":
        return f"عدد العناصر في «{label}» أكبر من المسموح"

    if error_type == "json_invalid":
        return "صيغة الطلب غير صحيحة"

    if error_type == "value_error":
        # Our own validators raise ValueError with Arabic messages
        # pydantic wraps it as "Value error, <our message>"
        if raw_msg.startswith("Value error, "):
            return raw_msg[len("Value error, "):]
        return raw_msg

    # Fallback
    return f"قيمة غير صالحة في الحقل «{label}»"


def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the exception with full trace, return 500 with a generic Arabic message."""
    logger.exception(
        "Unhandled exception: %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(
        {"detail": "حدث خطأ غير متوقع، حاول مرة أخرى أو راجع مسؤول النظام"},
        status_code=500
    )


def register_exception_handlers(app):
    """Register all custom exception handlers on the FastAPI app."""
    from fastapi import HTTPException as FastAPIHTTPException

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(FastAPIHTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
