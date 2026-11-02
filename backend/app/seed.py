import asyncio

from sqlalchemy.dialects.postgresql import insert

from app.core.database import SessionLocal, engine
from app.models import AppointmentCategory, Governorate, Role, User

ROLES = [
    ("CENTRAL_ADMIN", "مسؤول الإدارة المركزية"),
    ("CENTRAL_HR", "موارد بشرية مركزية"),
    ("DIRECTORATE_HR", "موارد بشرية مديرية"),
    ("EMPLOYEE", "موظف"),
]

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
        await db.commit()
    await engine.dispose()
    print("seed done")


if __name__ == "__main__":
    asyncio.run(main())