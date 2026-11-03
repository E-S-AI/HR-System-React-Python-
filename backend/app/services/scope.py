from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Employee, OrgUnit, User, UserScope

UNRESTRICTED_ROLES = {"CENTRAL_ADMIN", "CENTRAL_HR"}


@dataclass
class Scope:
    governorates: set[str]
    org_unit_ids: set[int]  # موسّعة مسبقاً بالوحدات الفرعية

    def allows(self, governorate_code: str | None, org_unit_id: int | None) -> bool:
        return governorate_code in self.governorates or (
            org_unit_id is not None and org_unit_id in self.org_unit_ids
        )

    def employee_filter(self):
        return or_(
            Employee.governorate_code.in_(list(self.governorates)),
            Employee.org_unit_id.in_(list(self.org_unit_ids)),
        )


def is_unrestricted(user: User) -> bool:
    return user.is_super_admin or bool({r.code for r in user.roles} & UNRESTRICTED_ROLES)


async def descendant_ids(db: AsyncSession, roots: set[int]) -> set[int]:
    child = aliased(OrgUnit)
    tree = (
        select(OrgUnit.id)
        .where(OrgUnit.id.in_(list(roots)))
        .cte("tree", recursive=True)
    )
    tree = tree.union_all(select(child.id).where(child.parent_id == tree.c.id))
    rows = await db.scalars(select(tree.c.id))
    return set(rows.all())


async def get_scope(db: AsyncSession, user: User) -> Scope | None:
    """None = بلا قيود. وإلا نطاق محدد (قد يكون فارغاً فيعني لا شيء)."""
    if is_unrestricted(user):
        return None
    rows = (
        await db.scalars(select(UserScope).where(UserScope.user_id == user.id))
    ).all()
    governorates = {r.governorate_code for r in rows if r.governorate_code}
    exact = {r.org_unit_id for r in rows if r.org_unit_id and not r.include_sub_units}
    roots = {r.org_unit_id for r in rows if r.org_unit_id and r.include_sub_units}
    unit_ids = set(exact)
    if roots:
        unit_ids |= await descendant_ids(db, roots)
    return Scope(governorates, unit_ids)