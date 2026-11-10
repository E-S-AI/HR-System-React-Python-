from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import User
from app.schemas.employee import (
    QualificationIn,
    QualificationRead,
    TrainingIn,
    TrainingRead,
)
from app.schemas.employee_files import (
    AssignmentEnd,
    AssignmentInput,
    AssignmentRead,
    QualificationPatch,
    TrainingPatch,
)
from app.services import assignments as assign_svc
from app.services import employee_files as svc

router = APIRouter(prefix="/employees", tags=["employee-files"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")


# ---------------------------------------------------------------- المؤهلات
@router.get("/{employee_id}/qualifications", response_model=list[QualificationRead])
async def list_qualifications(
    employee_id: int, db: AsyncSession = Depends(get_db), actor: User = Depends(hr_or_admin)
):
    return await svc.list_qualifications(db, actor, employee_id)


@router.post(
    "/{employee_id}/qualifications", response_model=QualificationRead, status_code=201
)
async def add_qualification(
    employee_id: int,
    data: QualificationIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await svc.add_qualification(db, actor, employee_id, data)


@router.patch(
    "/{employee_id}/qualifications/{qualification_id}", response_model=QualificationRead
)
async def patch_qualification(
    employee_id: int,
    qualification_id: int,
    data: QualificationPatch,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await svc.patch_qualification(db, actor, employee_id, qualification_id, data)


@router.delete("/{employee_id}/qualifications/{qualification_id}", status_code=204)
async def delete_qualification(
    employee_id: int,
    qualification_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    await svc.delete_qualification(db, actor, employee_id, qualification_id)


# ---------------------------------------------------------------- الدورات
@router.get("/{employee_id}/trainings", response_model=list[TrainingRead])
async def list_trainings(
    employee_id: int, db: AsyncSession = Depends(get_db), actor: User = Depends(hr_or_admin)
):
    return await svc.list_trainings(db, actor, employee_id)


@router.post("/{employee_id}/trainings", response_model=TrainingRead, status_code=201)
async def add_training(
    employee_id: int,
    data: TrainingIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await svc.add_training(db, actor, employee_id, data)


@router.patch("/{employee_id}/trainings/{training_id}", response_model=TrainingRead)
async def patch_training(
    employee_id: int,
    training_id: int,
    data: TrainingPatch,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await svc.patch_training(db, actor, employee_id, training_id, data)


@router.delete("/{employee_id}/trainings/{training_id}", status_code=204)
async def delete_training(
    employee_id: int,
    training_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    await svc.delete_training(db, actor, employee_id, training_id)


# ---------------------------------------------------------------- التكليفات
@router.get("/{employee_id}/assignments", response_model=list[AssignmentRead])
async def list_assignments(
    employee_id: int, db: AsyncSession = Depends(get_db), actor: User = Depends(hr_or_admin)
):
    return await assign_svc.list_assignments(db, actor, employee_id)


@router.post("/{employee_id}/assignments", response_model=AssignmentRead, status_code=201)
async def start_assignment(
    employee_id: int,
    data: AssignmentInput,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await assign_svc.start_assignment(db, actor, employee_id, data)


@router.post("/{employee_id}/assignments/renew", response_model=AssignmentRead, status_code=201)
async def renew_assignment(
    employee_id: int,
    data: AssignmentInput,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await assign_svc.renew_assignment(db, actor, employee_id, data)


@router.post("/{employee_id}/assignments/end", response_model=AssignmentRead, status_code=201)
async def end_assignment(
    employee_id: int,
    data: AssignmentEnd,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await assign_svc.end_assignment(db, actor, employee_id, data)