from datetime import date, datetime, timedelta, timezone
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AppointmentCategory,
    Employee,
    Governorate,
    ImportJob,
    LeaveRequest,
    LeaveType,
    User,
)
from app.schemas.dashboard import (
    AlertsCenter,
    DashboardSummary,
    DistributionItem,
    ExpiringAssignmentItem,
    ExpiringLeaveItem,
    LeaveKPIs,
    LockedUserItem,
    PendingLeaveBrief,
    RecentImportBrief,
    WorkforceKPIs,
)
from app.services.scope import get_scope
from app.services.users import is_admin


async def get_dashboard_summary(db: AsyncSession, actor: User) -> DashboardSummary:
    scope = await get_scope(db, actor)
    emp_conds = [scope.employee_filter()] if scope is not None else []

    today = date.today()
    now_utc = datetime.now(timezone.utc)
    in_12h = now_utc + timedelta(hours=12)
    in_15d = today + timedelta(days=15)

    # 1. مؤشرات القوة العاملة باستعلام واحد مجمّع
    has_acc_expr = exists().where(User.employee_id == Employee.id)
    wf_row = (
        await db.execute(
            select(
                func.count(Employee.id).label("total"),
                func.count(Employee.id)
                .filter(Employee.termination_date.is_(None))
                .label("active"),
                func.count(Employee.id)
                .filter(Employee.termination_date.is_not(None))
                .label("terminated"),
                func.count(Employee.id)
                .filter(Employee.permanent_or_contract == "مثبت")
                .label("permanent"),
                func.count(Employee.id)
                .filter(Employee.permanent_or_contract == "متعاقد")
                .label("contract"),
                func.count(Employee.id)
                .filter(
                    Employee.employee_code.is_(None),
                    Employee.termination_date.is_(None),
                )
                .label("missing_code"),
                func.count(Employee.id)
                .filter(
                    Employee.biometric_code.is_(None),
                    Employee.termination_date.is_(None),
                )
                .label("missing_bio"),
                func.count(Employee.id).filter(has_acc_expr).label("with_acc"),
            ).where(*emp_conds)
        )
    ).one()

    workforce = WorkforceKPIs(
        total_employees=wf_row.total,
        active_employees=wf_row.active,
        terminated_employees=wf_row.terminated,
        permanent_count=wf_row.permanent,
        contract_count=wf_row.contract,
        missing_code_count=wf_row.missing_code,
        missing_biometric_count=wf_row.missing_bio,
        with_account_count=wf_row.with_acc,
    )

    # 2. مؤشرات الإجازات والمهمات اللحظية
    lv_stmt = (
        select(
            func.count(LeaveRequest.id)
            .filter(LeaveRequest.status == "PENDING_HR_APPROVAL")
            .label("pending_hr"),
            func.count(LeaveRequest.id)
            .filter(LeaveRequest.status == "AWAITING_PAPER")
            .label("awaiting_paper"),
            func.count(LeaveRequest.id)
            .filter(
                LeaveRequest.status == "AWAITING_PAPER",
                LeaveRequest.attachment_deadline_at.is_not(None),
                LeaveRequest.attachment_deadline_at > now_utc,
                LeaveRequest.attachment_deadline_at <= in_12h,
            )
            .label("expiring_12h"),
            func.count(LeaveRequest.id)
            .filter(
                LeaveRequest.status == "APPROVED",
                LeaveType.code != "MISSION",
                LeaveRequest.start_date <= today,
                LeaveRequest.end_date >= today,
            )
            .label("on_leave_today"),
            func.count(LeaveRequest.id)
            .filter(
                LeaveRequest.status == "APPROVED",
                LeaveType.code == "MISSION",
                LeaveRequest.start_date <= today,
                LeaveRequest.end_date >= today,
            )
            .label("on_mission_today"),
        )
        .select_from(LeaveRequest)
        .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
        .join(Employee, Employee.id == LeaveRequest.employee_id)
        .where(*emp_conds)
    )
    lv_row = (await db.execute(lv_stmt)).one()

    leaves = LeaveKPIs(
        pending_hr_approval=lv_row.pending_hr,
        awaiting_paper=lv_row.awaiting_paper,
        expiring_within_12h=lv_row.expiring_12h,
        on_leave_today=lv_row.on_leave_today,
        on_mission_today=lv_row.on_mission_today,
    )

    # 3. صندوق التنبيهات: أ) التكليفات التي تنتهي خلال 15 يوماً
    exp_assign_rows = (
        await db.execute(
            select(
                Employee.id,
                Employee.full_name_spaced,
                Employee.employee_code,
                Employee.governorate_code,
                Employee.assignment_end_date,
            )
            .where(
                *emp_conds,
                Employee.termination_date.is_(None),
                Employee.assignment_end_date.is_not(None),
                Employee.assignment_end_date >= today,
                Employee.assignment_end_date <= in_15d,
            )
            .order_by(Employee.assignment_end_date.asc())
            .limit(20)
        )
    ).all()

    expiring_assignments = [
        ExpiringAssignmentItem(
            employee_id=r.id,
            full_name_spaced=r.full_name_spaced,
            employee_code=r.employee_code,
            governorate_code=r.governorate_code,
            assignment_end_date=r.assignment_end_date,
            days_remaining=(r.assignment_end_date - today).days,
        )
        for r in exp_assign_rows
    ]

    # 3. ب) الحسابات المقفلة حالياً
    locked_stmt = (
        select(
            User.id,
            User.phone_number,
            User.employee_id,
            Employee.full_name_spaced,
            User.locked_until,
        )
        .outerjoin(Employee, Employee.id == User.employee_id)
        .where(User.locked_until.is_not(None), User.locked_until > now_utc)
        .order_by(User.locked_until.desc())
        .limit(20)
    )
    if scope is not None:
        locked_stmt = locked_stmt.where(scope.employee_filter())
    locked_rows = (await db.execute(locked_stmt)).all()

    locked_users = [
        LockedUserItem(
            user_id=r.id,
            phone_number=r.phone_number,
            employee_id=r.employee_id,
            employee_name=r.full_name_spaced,
            locked_until=r.locked_until,
        )
        for r in locked_rows
    ]

    # 3. ج) طلبات الإجازة التي تقترب من الرفض الآلي (أقل من 12 ساعة)
    exp_leave_rows = (
        await db.execute(
            select(
                LeaveRequest.id,
                LeaveRequest.employee_id,
                Employee.full_name_spaced,
                LeaveType.name_ar,
                LeaveRequest.attachment_deadline_at,
            )
            .join(Employee, Employee.id == LeaveRequest.employee_id)
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(
                *emp_conds,
                LeaveRequest.status == "AWAITING_PAPER",
                LeaveRequest.attachment_deadline_at.is_not(None),
                LeaveRequest.attachment_deadline_at > now_utc,
                LeaveRequest.attachment_deadline_at <= in_12h,
            )
            .order_by(LeaveRequest.attachment_deadline_at.asc())
            .limit(20)
        )
    ).all()

    expiring_leaves_12h = [
        ExpiringLeaveItem(
            request_id=r.id,
            employee_id=r.employee_id,
            employee_name=r.full_name_spaced,
            leave_type_name_ar=r.name_ar,
            attachment_deadline_at=r.attachment_deadline_at,
            hours_remaining=round(
                (r.attachment_deadline_at - now_utc).total_seconds() / 3600, 1
            ),
        )
        for r in exp_leave_rows
    ]

    # 4. التوزيع الجغرافي حسب المحافظات الـ 14
    gov_rows = (
        await db.execute(
            select(
                Governorate.governorate_code,
                Governorate.governorate_name_ar,
                func.count(Employee.id).label("cnt"),
            )
            .outerjoin(
                Employee,
                (Employee.governorate_code == Governorate.governorate_code)
                & (Employee.termination_date.is_(None)),
            )
            .where(*(emp_conds if scope is not None else []))
            .group_by(
                Governorate.id,
                Governorate.governorate_code,
                Governorate.governorate_name_ar,
            )
            .order_by(func.count(Employee.id).desc(), Governorate.id)
        )
    ).all()

    by_governorate = [
        DistributionItem(
            code=r.governorate_code, label_ar=r.governorate_name_ar, count=r.cnt
        )
        for r in gov_rows
    ]

    # 5. التوزيع حسب فئات التعيين الـ 6
    cat_rows = (
        await db.execute(
            select(
                AppointmentCategory.category_code,
                AppointmentCategory.category_label_ar,
                func.count(Employee.id).label("cnt"),
            )
            .outerjoin(
                Employee,
                (Employee.appointment_category_code == AppointmentCategory.category_code)
                & (Employee.termination_date.is_(None)),
            )
            .where(*(emp_conds if scope is not None else []))
            .group_by(
                AppointmentCategory.id,
                AppointmentCategory.category_code,
                AppointmentCategory.category_label_ar,
            )
            .order_by(AppointmentCategory.id)
        )
    ).all()

    by_category = [
        DistributionItem(
            code=r.category_code, label_ar=r.category_label_ar, count=r.cnt
        )
        for r in cat_rows
    ]

    # 6. أحدث 10 طلبات مرفوعة الورقة وبانتظار قرار HR
    pending_rows = (
        await db.execute(
            select(
                LeaveRequest.id,
                LeaveRequest.employee_id,
                Employee.full_name_spaced,
                Employee.employee_code,
                Employee.governorate_code,
                LeaveType.code,
                LeaveType.name_ar,
                LeaveRequest.start_date,
                LeaveRequest.end_date,
                LeaveRequest.duration_days,
                LeaveRequest.duration_minutes,
                LeaveRequest.attachment_uploaded_at,
            )
            .join(Employee, Employee.id == LeaveRequest.employee_id)
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(*emp_conds, LeaveRequest.status == "PENDING_HR_APPROVAL")
            .order_by(LeaveRequest.attachment_uploaded_at.asc())
            .limit(10)
        )
    ).all()

    recent_pending_leaves = [
        PendingLeaveBrief(
            request_id=r.id,
            employee_id=r.employee_id,
            employee_name=r.full_name_spaced,
            employee_code=r.employee_code,
            governorate_code=r.governorate_code,
            leave_type_code=r.code,
            leave_type_name_ar=r.name_ar,
            start_date=r.start_date,
            end_date=r.end_date,
            duration_days=float(r.duration_days),
            duration_minutes=r.duration_minutes,
            attachment_uploaded_at=r.attachment_uploaded_at,
        )
        for r in pending_rows
    ]

    # 7. أحدث 5 عمليات استيراد Excel
    imp_stmt = select(ImportJob).order_by(ImportJob.id.desc()).limit(5)
    if not is_admin(actor):
        imp_stmt = imp_stmt.where(ImportJob.created_by_user_id == actor.id)
    imp_rows = (await db.scalars(imp_stmt)).all()

    recent_imports = [
        RecentImportBrief(
            job_id=j.id,
            original_file_name=j.original_file_name,
            status=j.status,
            total_rows=j.total_rows,
            valid_new_rows=j.valid_new_rows,
            error_rows=j.error_rows,
            created_at=j.created_at,
        )
        for j in imp_rows
    ]

    return DashboardSummary(
        workforce=workforce,
        leaves=leaves,
        alerts=AlertsCenter(
            expiring_assignments=expiring_assignments,
            locked_users=locked_users,
            expiring_leaves_12h=expiring_leaves_12h,
        ),
        by_governorate=by_governorate,
        by_category=by_category,
        recent_pending_leaves=recent_pending_leaves,
        recent_imports=recent_imports,
    )