from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.employees import router as employees_router
from app.core.database import get_db
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.org import router as org_router
from app.api.imports import router as imports_router
from app.api.lookups import router as lookups_router
from app.api.exports import router as exports_router
from app.api.leave_balances import router as leave_balances_router
from app.api.work_schedules import router as work_schedules_router
from app.api.leave_requests import router as leave_requests_router
from app.api.leave_forms import router as leave_forms_router
from app.api.public_holidays import router as public_holidays_router
from app.api.dashboard import router as dashboard_router
from app.api.employee_files import router as employee_files_router

app = FastAPI(title="Centralized HRMS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(employees_router)
app.include_router(employee_files_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(org_router)
app.include_router(imports_router)
app.include_router(lookups_router)
app.include_router(exports_router)
app.include_router(work_schedules_router)
app.include_router(leave_balances_router)
app.include_router(leave_requests_router)
app.include_router(leave_forms_router)
app.include_router(public_holidays_router)
app.include_router(dashboard_router)



@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("select version()"))
    return {"db": "ok", "version": result.scalar()}