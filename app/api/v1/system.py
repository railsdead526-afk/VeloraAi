from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
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
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc

    return {
        "status": "ready",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/info")
def app_info():
    return {
        "app_name": settings.app_name,
        "version": "0.1.1",
        "environment": settings.app_env,
        "ai_provider": settings.ai_provider,
    }


@router.get("/search")
def search(q: str | None = None, limit: int = 10):
    safe_limit = max(1, min(limit, 50))
    return {"query": q, "limit": safe_limit, "results": []}
