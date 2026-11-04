import asyncio
from datetime import date, time

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.core.database import SessionLocal, engine
from app.models import (
    AppointmentCategory,
    Governorate,
    LeaveType,
    Role,
    ServiceLeaveTier,
    WorkSchedule,
)

GOVERNORATES = [
    ("ادلب", "Idlib", "ID"),
    ("الحسكة", "Al Hasakah", "AH"),
    ("السويداء", "As Suwayda", "AS"),
    ("اللاذقية", "Latakia", "LA"),
    ("حلب", "Aleppo", "AP"),
    ("حماه", "Hama", "HA"),
    ("حمص", "Homs", "HO"),
    ("درعا", "Daraa", "DA"),
    ("دمشق", "Damascus", "DM"),
    ("ريف دمشق", "Damascus Suburb", "DS"),
    ("طرطوس", "Tartus", "TA"),
    ("دير الزور", "Deir ez-Zor", "DZ"),
    ("الرقة", "Al-Raqqah", "RQ"),
    ("القنيطرة", "Quneitra", "QU"),
]

CATEGORIES = [
    ("Aa", "حكومة الإنقاذ - مثبت", "مثبت"),
    ("A", "حكومة الإنقاذ - متعاقد", "متعاقد"),
    ("B", "متعاقد جديد بعد التحرير", "متعاقد"),
    ("Bb", "مثبت جديد بعد التحرير", "مثبت"),
    ("Cc", "حكومة النظام السابق - مثبت", "مثبت"),
    ("C", "حكومة النظام السابق - متعاقد", "متعاقد"),
]

ROLES = [
    ("CENTRAL_ADMIN", "مسؤول الإدارة المركزية"),
    ("CENTRAL_HR", "موارد بشرية مركزية"),
    ("DIRECTORATE_HR", "موارد بشرية مديرية"),
    ("EMPLOYEE", "موظف"),
]

PAPER = "EMPLOYEE_PAPER_THEN_HR"
HR_ONLY = "HR_DIRECT_DECISION"
# code, name, employee_request, workflow, deducts_balance, min, max, enforce_72h, past_h, grace_h
LEAVE_TYPES = [
    ("ADMIN", "إدارية", True, PAPER, True, None, None, True, 72, 72),
    ("HOURLY", "ساعية", True, PAPER, True, 60, 120, True, 72, 72),
    ("MISSION", "مهمة", True, PAPER, False, None, None, False, None, None),
    ("UNPAID", "بلا أجر", False, HR_ONLY, False, None, None, False, None, None),
    ("SICK", "صحية", False, HR_ONLY, False, None, None, False, None, None),
    ("MARRIAGE", "زواج", False, HR_ONLY, False, None, None, False, None, None),
    ("DEATH", "وفاة", False, HR_ONLY, False, None, None, False, None, None),
    ("HAJJ", "حج", False, HR_ONLY, False, None, None, False, None, None),
]

# (من، إلى غير شامل، أيام)
ADMIN_TIERS = [(0, 5, 15), (5, 10, 21), (10, 20, 26), (20, None, 30)]


async def main() -> None:
    async with SessionLocal() as db:
        await db.execute(
            insert(Governorate)
            .values(
                [
                    {"governorate_name_ar": ar, "governorate_name_en": en, "governorate_code": code}
                    for ar, en, code in GOVERNORATES
                ]
            )
            .on_conflict_do_nothing(index_elements=["governorate_code"])
        )
        await db.execute(
            insert(AppointmentCategory)
            .values(
                [
                    {"category_code": code, "category_label_ar": label, "employment_type": emp}
                    for code, label, emp in CATEGORIES
                ]
            )
            .on_conflict_do_nothing(index_elements=["category_code"])
        )
        await db.execute(
            insert(Role)
            .values([{"code": c, "name_ar": n} for c, n in ROLES])
            .on_conflict_do_nothing(index_elements=["code"])
        )
        await db.execute(
            insert(LeaveType)
            .values(
                [
                    {
                        "code": code,
                        "name_ar": name,
                        "allow_employee_request": req,
                        "workflow_path": wf,
                        "deducts_balance": ded,
                        "min_duration_minutes": mn,
                        "max_duration_minutes": mx,
                        "enforce_72h_rule": e72,
                        "max_past_entry_hours": past,
                        "paper_upload_grace_hours": grace,
                    }
                    for code, name, req, wf, ded, mn, mx, e72, past, grace in LEAVE_TYPES
                ]
            )
            .on_conflict_do_nothing(index_elements=["code"])
        )
        await db.execute(
            text(
                "UPDATE leave_types SET deducts_from_type_id = "
                "(SELECT id FROM leave_types WHERE code = 'ADMIN') WHERE code = 'HOURLY'"
            )
        )
        admin_id = await db.scalar(select(LeaveType.id).where(LeaveType.code == "ADMIN"))
        await db.execute(
            insert(ServiceLeaveTier)
            .values(
                [
                    {
                        "leave_type_id": admin_id,
                        "min_service_years": lo,
                        "max_service_years": hi,
                        "entitled_days": days,
                    }
                    for lo, hi, days in ADMIN_TIERS
                ]
            )
            .on_conflict_do_nothing(index_elements=["leave_type_id", "min_service_years"])
        )
        if not await db.scalar(select(func.count()).select_from(WorkSchedule)):
            db.add(
                WorkSchedule(
                    schedule_name_ar="الدوام الرسمي (08:00 - 15:00)",
                    official_start_time=time(8, 0),
                    official_end_time=time(15, 0),
                    late_grace_minutes=20,
                    early_leave_grace_minutes=20,
                    late_cutoff_time=time(8, 20),
                    early_leave_cutoff_time=time(14, 40),
                    workday_minutes=420,
                    effective_from_date=date(2020, 1, 1),
                )
            )
        await db.commit()
    await engine.dispose()
    print("seed done")


if __name__ == "__main__":
    asyncio.run(main())