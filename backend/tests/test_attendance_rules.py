"""
Pure-logic tests for the attendance deduction engine (no DB, no I/O).
Tests compute_day() and net_deduction_minutes() from app.services.attendance.
"""
from datetime import time

import pytest

from app.services.attendance import compute_day, net_deduction_minutes

# default schedule constants used in production
OFFICIAL_START = time(8, 0)
OFFICIAL_END = time(15, 0)
LATE_CUTOFF = time(8, 20)
EARLY_CUTOFF = time(14, 40)


def day(first_in=None, last_out=None):
    return compute_day(
        first_in, last_out, OFFICIAL_START, OFFICIAL_END, LATE_CUTOFF, EARLY_CUTOFF
    )


# ---------------------------------------------------------------------------
# on-time employees
# ---------------------------------------------------------------------------

def test_present_exact_times():
    d = day(time(8, 0), time(15, 0))
    assert d.status == "PRESENT"
    assert d.late_minutes == 0
    assert d.early_leave_minutes == 0
    assert d.gross_charged_minutes == 0


def test_present_slightly_late_no_cutoff():
    """10 minutes late — before cutoff → not charged, still PRESENT."""
    d = day(time(8, 10), time(15, 0))
    assert d.late_minutes == 10
    assert not d.is_late_beyond_cutoff
    assert d.gross_charged_minutes == 0
    assert d.status == "PRESENT"


def test_present_slightly_early_no_cutoff():
    """Leave at 14:50 — after early cutoff (14:40) → not charged."""
    d = day(time(8, 0), time(14, 50))
    assert d.early_leave_minutes == 10
    assert not d.is_early_leave_beyond_cutoff
    assert d.gross_charged_minutes == 0
    assert d.status == "PRESENT"


# ---------------------------------------------------------------------------
# late beyond cutoff
# ---------------------------------------------------------------------------

def test_late_exactly_at_cutoff():
    """Arrive exactly at 08:20 → triggers deduction."""
    d = day(time(8, 20), time(15, 0))
    assert d.is_late_beyond_cutoff
    assert d.late_minutes == 20
    assert d.gross_charged_minutes == 20
    assert d.status == "LATE"


def test_late_30_minutes():
    d = day(time(8, 30), time(15, 0))
    assert d.is_late_beyond_cutoff
    assert d.late_minutes == 30
    assert d.gross_charged_minutes == 30
    assert d.status == "LATE"


# ---------------------------------------------------------------------------
# early leave beyond cutoff
# ---------------------------------------------------------------------------

def test_early_leave_exactly_at_cutoff():
    """Leave exactly at 14:40 → triggers deduction."""
    d = day(time(8, 0), time(14, 40))
    assert d.is_early_leave_beyond_cutoff
    assert d.early_leave_minutes == 20
    assert d.gross_charged_minutes == 20
    assert d.status == "EARLY_LEAVE"


def test_early_leave_one_hour():
    d = day(time(8, 0), time(14, 0))
    assert d.is_early_leave_beyond_cutoff
    assert d.early_leave_minutes == 60
    assert d.gross_charged_minutes == 60
    assert d.status == "EARLY_LEAVE"


# ---------------------------------------------------------------------------
# both late and early
# ---------------------------------------------------------------------------

def test_late_and_early():
    d = day(time(8, 25), time(14, 30))
    assert d.is_late_beyond_cutoff
    assert d.is_early_leave_beyond_cutoff
    assert d.late_minutes == 25
    assert d.early_leave_minutes == 30
    assert d.gross_charged_minutes == 55
    assert d.status == "LATE_AND_EARLY"


# ---------------------------------------------------------------------------
# missing punch
# ---------------------------------------------------------------------------

def test_missing_punch_both_none():
    d = day(None, None)
    assert d.status == "MISSING_PUNCH"
    assert d.gross_charged_minutes == 0


def test_missing_first_in_only():
    """Only last_out punched → MISSING_PUNCH, no auto-charge (needs review)."""
    d = day(None, time(14, 0))
    assert d.late_minutes == 0
    assert d.early_leave_minutes == 60
    assert d.gross_charged_minutes == 0
    assert d.status == "MISSING_PUNCH"


def test_missing_last_out_only():
    """Only first_in punched → MISSING_PUNCH, no auto-charge (needs review)."""
    d = day(time(8, 25), None)
    assert d.late_minutes == 25
    assert d.early_leave_minutes == 0
    assert d.gross_charged_minutes == 0
    assert d.status == "MISSING_PUNCH"


# ---------------------------------------------------------------------------
# net_deduction_minutes (double-deduction guard)
# ---------------------------------------------------------------------------

def test_net_deduction_no_hourly():
    assert net_deduction_minutes(30, 0) == 30


def test_net_deduction_partial_hourly():
    """60 gross, 30 approved hourly → 30 charged."""
    assert net_deduction_minutes(60, 30) == 30


def test_net_deduction_full_coverage():
    """Approved hourly >= gross → 0 net deduction."""
    assert net_deduction_minutes(30, 60) == 0


def test_net_deduction_exact_coverage():
    assert net_deduction_minutes(30, 30) == 0


def test_net_deduction_no_negative():
    """Never returns a negative value."""
    assert net_deduction_minutes(0, 120) == 0


# ---------------------------------------------------------------------------
# different schedule parameters
# ---------------------------------------------------------------------------

def test_longer_day_schedule():
    """Leave 10 min early but after the early-leave cutoff → not charged."""
    d = compute_day(
        time(8, 0),
        time(14, 55),
        official_start=time(8, 0),
        official_end=time(15, 0),
        late_cutoff=time(8, 20),
        early_cutoff=time(14, 40),  # standard cutoff
    )
    # 14:55 > 14:40 → NOT beyond early cutoff
    assert d.early_leave_minutes == 5
    assert not d.is_early_leave_beyond_cutoff
    assert d.gross_charged_minutes == 0


def test_custom_late_cutoff():
    """Schedule with 08:30 late cutoff; arrive at 08:25 → late but NOT charged."""
    d = compute_day(
        time(8, 25),
        time(15, 0),
        official_start=time(8, 0),
        official_end=time(15, 0),
        late_cutoff=time(8, 30),
        early_cutoff=time(14, 40),
    )
    assert d.late_minutes == 25
    assert not d.is_late_beyond_cutoff
    assert d.gross_charged_minutes == 0
    assert d.status == "PRESENT"
