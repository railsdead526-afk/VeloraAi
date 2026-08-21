from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.config import settings
from app.core.plans import get_plan_policy
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.schemas.token import Token
from app.crud.user import get_user_by_email, create_user, authenticate_user
from app.core.security import create_access_token
from app.services.quota_service import requests_used_since

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_auth)
def register(request: Request, user_in: UserCreate, db: Session = Depends(get_db)):
    existing_user = get_user_by_email(db, user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    return create_user(db, user_in.email, user_in.password)


@router.post("/login", response_model=Token)
@limiter.limit(settings.rate_limit_auth)
def login(request: Request, user_in: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, user_in.email, user_in.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = create_access_token(data={"sub": user.email})

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    policy = get_plan_policy(getattr(current_user, "role", None))
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    next_reset = day_start + timedelta(days=1)
    daily_used = requests_used_since(db, current_user.id, day_start)

    return {
        "id": current_user.id,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "role": current_user.role,
        "daily_requests_used": daily_used,
        "daily_request_limit": policy.daily_request_limit,
        "daily_reset_at": next_reset,
    }


@router.get("/premium-only", response_model=UserResponse)
def premium_only(current_user=Depends(require_roles("pro", "max", "admin"))):
    return current_user


@router.get("/admin-only", response_model=UserResponse)
def admin_only(current_user=Depends(require_roles("admin"))):
    return current_user
