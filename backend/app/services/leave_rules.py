import calendar
from datetime import date, datetime, time, timedelta

# الجمعة والسبت عطلة أسبوعية (الاثنين = 0)
WEEKEND_WEEKDAYS = frozenset({4, 5})
NO_HOLIDAYS: frozenset = frozenset()


def is_workday(d: date, holidays=NO_HOLIDAYS) -> bool:
    """يوم عمل: ليس عطلة أسبوعية وليس عطلة رسمية."""
    return d.weekday() not in WEEKEND_WEEKDAYS and d not in holidays


def iter_days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def working_days(start: date, end: date, holidays=NO_HOLIDAYS) -> list[date]:
    return [d for d in iter_days(start, end) if is_workday(d, holidays)]


def next_workday(d: date, holidays=NO_HOLIDAYS) -> date:
    d += timedelta(days=1)
    while not is_workday(d, holidays):
        d += timedelta(days=1)
    return d


def add_months(d: date, months: int) -> date:
    y, m0 = divmod(d.year * 12 + (d.month - 1) + months, 12)
    m = m0 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


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


def admin_minutes(schedules, start: date, end: date, holidays=NO_HOLIDAYS) -> tuple[int, list[date]]:
    days = working_days(start, end, holidays)
    total = 0
    for d in days:
        s = schedule_for(schedules, d)
        if s is None:
            raise ValueError(f"لا يوجد جدول دوام ساري بتاريخ {d.isoformat()}")
        total += s.workday_minutes
    return total, days


def consecutive_run_over_limit(new_days, existing_days, limit: int, holidays=NO_HOLIDAYS):
    """أيام العمل المتتالية: العطلة الأسبوعية والرسمية لا تقطع التتابع.
    يرجع (أول يوم في السلسلة، طولها) لأول سلسلة تضم يوماً جديداً وتتجاوز الحد، أو None."""
    new_set = set(new_days)
    runs: list[list[date]] = []
    run: list[date] = []
    for d in sorted(new_set | set(existing_days)):
        if run and next_workday(run[-1], holidays) == d:
            run.append(d)
        else:
            if run:
                runs.append(run)
            run = [d]
    if run:
        runs.append(run)
    for r in runs:
        if len(r) > limit and any(d in new_set for d in r):
            return r[0], len(r)
    return None


def charged_hourly_minutes(actual: int, lo: int | None, hi: int | None) -> int:
    """أقل من الحد الأدنى يُحسب الحد الأدنى. أكثر من الحد الأقصى مرفوض (ValueError)."""
    if actual <= 0:
        raise ValueError("وقت النهاية يجب أن يكون بعد وقت البداية")
    if hi and actual > hi:
        raise ValueError("over_max")
    return max(actual, lo) if lo else actual