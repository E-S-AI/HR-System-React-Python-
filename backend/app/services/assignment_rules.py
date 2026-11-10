from datetime import date


def duration_text(start: date, end: date | None) -> str | None:
    """مدة التكليف بالأيام (شاملة اليومين) عند معرفة تاريخ الانتهاء."""
    if end is None:
        return None
    return f"{(end - start).days + 1} يوماً"


def renewal_date_error(prev_start: date, prev_end: date | None, new_start: date) -> str | None:
    if new_start < prev_start:
        return "تاريخ بدء التجديد قبل تاريخ بدء التكليف الحالي"
    if prev_end is not None and new_start < prev_end:
        return "تاريخ بدء التجديد قبل انتهاء التكليف الحالي، ابدأ التجديد في تاريخ الانتهاء أو بعده"
    return None


def end_date_error(start: date, end: date) -> str | None:
    if end < start:
        return "تاريخ الإنهاء قبل تاريخ بدء التكليف"
    return None