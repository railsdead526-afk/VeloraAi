from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db

router = APIRouter(tags=["System"])


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        required_tables = {"users", "conversations", "messages", "documents", "payments"}
        if db.bind.dialect.name == "postgresql":
            table_query = text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name IN :tables"
            ).bindparams(bindparam("tables", expanding=True))
        else:
            table_query = text(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN :tables"
            ).bindparams(bindparam("tables", expanding=True))
        table_rows = db.execute(table_query, {"tables": list(required_tables)}).scalars().all()
        missing_tables = required_tables - set(table_rows)
        if missing_tables:
            raise RuntimeError(f"Missing required database tables: {sorted(missing_tables)}")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable or schema is incomplete",
        ) from exc

    return {
        "status": "ready",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/info")
def info():
    return {
        "service": settings.app_name,
        "environment": settings.app_env,
    }
