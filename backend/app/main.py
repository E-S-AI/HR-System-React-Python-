from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.employees import router as employees_router
from app.core.database import get_db
from app.api.auth import router as auth_router


app = FastAPI(title="Centralized HRMS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(employees_router)
app.include_router(auth_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("select version()"))
    return {"db": "ok", "version": result.scalar()}