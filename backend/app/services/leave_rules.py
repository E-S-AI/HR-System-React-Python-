from datetime import date, datetime, time, timedelta

# الجمعة والسبت عطلة أسبوعية (الاثنين = 0)
WEEKEND_WEEKDAYS = frozenset({4, 5})


def is_workday(d: date) -> bool:
    return d.weekday() not in WEEKEND_WEEKDAYS


def iter_days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def working_days(start: date, end: date) -> list[date]:
    return [d for d in iter_days(start, end) if is_workday(d)]


def time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def minutes_between(t1: time, t2: time) -> int:
    return time_to_minutes(t2) - time_to_minutes(t1)


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def is_too_old(start_dt: datetime, now: datetime, max_hours: int) -> bool:
    """True إذا كان بدء الطلب أقدم من (الآن - max_hours)."""
    return start_dt < now - timedelta(hours=max_hours)


def schedule_for(schedules, day: date):
    for s in schedules:
        if s.effective_from_date <= day and (
            s.effective_to_date is None or s.effective_to_date >= day
        ):
            return s
    return None


def admin_minutes(schedules, start: date, end: date) -> tuple[int, list[date]]:
    days = working_days(start, end)
    total = 0
    for d in days:
        s = schedule_for(schedules, d)
        if s is None:
            raise ValueError(f"لا يوجد جدول دوام ساري بتاريخ {d.isoformat()}")
        total += s.workday_minutes
    return total, days