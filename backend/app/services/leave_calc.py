from datetime import date
from decimal import Decimal

from app.models import ServiceLeaveTier


def months_between(start: date, ref: date) -> int:
    months = (ref.year - start.year) * 12 + ref.month - start.month
    if ref.day < start.day:
        months -= 1
    return max(months, 0)


def completed_years(start: date, ref: date) -> int:
    return months_between(start, ref) // 12


def service_years_decimal(start: date, ref: date) -> Decimal:
    return (Decimal(months_between(start, ref)) / 12).quantize(Decimal("0.1"))


def pick_tier(tiers: list[ServiceLeaveTier], years: int) -> ServiceLeaveTier | None:
    for t in tiers:
        if years >= t.min_service_years and (
            t.max_service_years is None or years < t.max_service_years
        ):
            return t
    return None