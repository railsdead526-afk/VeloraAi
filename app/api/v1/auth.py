"""Authentication endpoints.

Design notes:
  * Access tokens are short lived and carry a `jti` so logout is real.
  * Refresh tokens are opaque, hashed at rest, and rotate on every use.
  * Enumeration is avoided: password-reset always answers 202, and login
    always answers with the same 401 regardless of which factor failed.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.core.plans import get_plan_policy
from app.core.rate_limit import limiter
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    get_password_hash,
    needs_rehash,
    new_jti,
    verify_password,
)
from app.crud.user import create_user, get_user_by_email
from app.schemas.token import LogoutRequest, RefreshRequest, Token
from app.schemas.user import (
    EmailVerificationRequest,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    SessionResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    next_daily_reset,
)
from app.services.audit_service import record_audit_event_best_effort
from app.services.auth_tokens import (
    PURPOSE_EMAIL_VERIFICATION,
    PURPOSE_PASSWORD_RESET,
    clear_failed_attempts,
    consume_verification_token,
    is_locked_out,
    issue_refresh_token,
    issue_verification_token,
    list_sessions,
    record_login_attempt,
    revoke_access_token,
    revoke_all_sessions,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.services.data_export import render_export
from app.services.notification_service import (
    send_password_reset_email,
    send_verification_email,
)
from app.services.quota_service import requests_used_since

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password",
)


def _user_payload(db: Session, user) -> dict:
    policy = get_plan_policy(getattr(user, "role", None))
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "role": user.role,
        "email_verified": user.is_email_verified,
        "daily_requests_used": requests_used_since(db, user.id, day_start),
        "daily_request_limit": policy.daily_request_limit,
        "daily_reset_at": next_daily_reset(now),
    }


def _issue_tokens(db: Session, user, request: Request) -> Token:
    access_token = create_access_token(
        data={"sub": user.email, "uid": user.id, "role": user.role},
        jti=new_jti(),
    )
    refresh_token = issue_refresh_token(
        db,
        user_id=user.id,
        user_agent=request.headers.get("User-Agent"),
        ip=client_ip(request),
    )
    return Token(
        access_token=access_token,
        token_type="bearer",  # noqa: S106
        expires_in=settings.access_token_expire_minutes * 60,
        refresh_token=refresh_token,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_auth)
def register(request: Request, user_in: UserCreate, db: Session = Depends(get_db)):
    if get_user_by_email(db, user_in.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = create_user(db, user_in.email, user_in.password)
    token = issue_verification_token(db, user_id=user.id, purpose=PURPOSE_EMAIL_VERIFICATION)
    send_verification_email(email=user.email, token=token)
    record_audit_event_best_effort(user_id=user.id, event="auth.register")
    return _user_payload(db, user)


@router.post("/login", response_model=Token)
@limiter.limit(settings.rate_limit_auth)
def login(request: Request, user_in: UserLogin, db: Session = Depends(get_db)):
    ip = client_ip(request)

    if is_locked_out(db, email=user_in.email):
        record_audit_event_best_effort(user_id=None, event="auth.login", status="locked_out")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again later.",
            headers={"Retry-After": str(settings.login_lockout_minutes * 60)},
        )

    user = get_user_by_email(db, user_in.email)
    password_ok = user is not None and verify_password(user_in.password, user.hashed_password)

    if not user or not password_ok or not user.is_active or user.is_deleted:
        record_login_attempt(db, email=user_in.email, ip=ip, successful=False)
        record_audit_event_best_effort(
            user_id=user.id if user else None, event="auth.login", status="failed"
        )
        raise _INVALID_CREDENTIALS

    if settings.require_email_verification and not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email address before signing in",
        )

    # Transparent upgrade from the legacy pbkdf2 hashes.
    if needs_rehash(user.hashed_password):
        user.hashed_password = get_password_hash(user_in.password)

    user.last_login_at = datetime.now(UTC)
    db.commit()

    record_login_attempt(db, email=user_in.email, ip=ip, successful=True)
    clear_failed_attempts(db, email=user_in.email)
    record_audit_event_best_effort(user_id=user.id, event="auth.login")
    return _issue_tokens(db, user, request)


@router.post("/refresh", response_model=Token)
@limiter.limit(settings.rate_limit_auth)
def refresh(request: Request, payload: RefreshRequest, db: Session = Depends(get_db)):
    rotated = rotate_refresh_token(
        db,
        token=payload.refresh_token,
        user_agent=request.headers.get("User-Agent"),
        ip=client_ip(request),
    )
    if rotated is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or expired",
        )

    user, new_refresh = rotated
    access_token = create_access_token(
        data={"sub": user.email, "uid": user.id, "role": user.role},
        jti=new_jti(),
    )
    record_audit_event_best_effort(user_id=user.id, event="auth.refresh")
    return Token(
        access_token=access_token,
        token_type="bearer",  # noqa: S106
        expires_in=settings.access_token_expire_minutes * 60,
        refresh_token=new_refresh,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    payload: LogoutRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Revoke the presented access token, and one or all refresh sessions."""
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        try:
            claims = decode_access_token(authorization.split(" ", 1)[1])
            revoke_access_token(
                db,
                jti=claims.get("jti", ""),
                user_id=current_user.id,
                expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
                reason="logout",
            )
        except (TokenError, KeyError, ValueError, OSError):
            pass

    if payload.all_sessions:
        revoked = revoke_all_sessions(db, user_id=current_user.id)
    elif payload.refresh_token:
        revoked = int(revoke_refresh_token(db, token=payload.refresh_token))
    else:
        revoked = 0

    record_audit_event_best_effort(
        user_id=current_user.id,
        event="auth.logout",
        metadata={"all_sessions": payload.all_sessions, "sessions_revoked": revoked},
    )
    return {"status": "ok", "sessions_revoked": revoked}


@router.get("/sessions", response_model=list[SessionResponse])
def sessions(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return list_sessions(db, user_id=current_user.id)


@router.post("/verify-email", status_code=status.HTTP_200_OK)
@limiter.limit(settings.rate_limit_auth)
def verify_email(
    request: Request, payload: EmailVerificationRequest, db: Session = Depends(get_db)
):
    user = consume_verification_token(db, token=payload.token, purpose=PURPOSE_EMAIL_VERIFICATION)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token is invalid or expired",
        )
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
        db.commit()
    record_audit_event_best_effort(user_id=user.id, event="auth.email_verified")
    return {"status": "verified"}


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/hour")
def resend_verification(
    request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    if current_user.is_email_verified:
        return {"status": "already_verified"}
    token = issue_verification_token(
        db, user_id=current_user.id, purpose=PURPOSE_EMAIL_VERIFICATION
    )
    send_verification_email(email=current_user.email, token=token)
    return {"status": "sent"}


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/hour")
def request_password_reset(
    request: Request, payload: PasswordResetRequest, db: Session = Depends(get_db)
):
    """Always returns 202 so the endpoint cannot be used to enumerate accounts."""
    user = get_user_by_email(db, payload.email)
    if user and user.is_active and not user.is_deleted:
        token = issue_verification_token(db, user_id=user.id, purpose=PURPOSE_PASSWORD_RESET)
        send_password_reset_email(email=user.email, token=token)
        record_audit_event_best_effort(user_id=user.id, event="auth.password_reset_requested")
    return {"status": "accepted"}


@router.post("/password-reset/confirm", status_code=status.HTTP_200_OK)
@limiter.limit(settings.rate_limit_auth)
def confirm_password_reset(
    request: Request, payload: PasswordResetConfirm, db: Session = Depends(get_db)
):
    user = consume_verification_token(db, token=payload.token, purpose=PURPOSE_PASSWORD_RESET)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid or expired",
        )

    user.hashed_password = get_password_hash(payload.new_password)
    user.password_changed_at = datetime.now(UTC)
    db.commit()

    # A password change must terminate every existing session.
    revoke_all_sessions(db, user_id=user.id, reason="password_reset")
    clear_failed_attempts(db, email=user.email)
    record_audit_event_best_effort(user_id=user.id, event="auth.password_reset_completed")
    return {"status": "password_updated"}


@router.post("/password", status_code=status.HTTP_200_OK)
@limiter.limit(settings.rate_limit_auth)
def change_password(
    request: Request,
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from the current password",
        )

    current_user.hashed_password = get_password_hash(payload.new_password)
    current_user.password_changed_at = datetime.now(UTC)
    db.commit()

    revoke_all_sessions(db, user_id=current_user.id, reason="password_change")
    record_audit_event_best_effort(user_id=current_user.id, event="auth.password_changed")
    return {"status": "password_updated"}


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_payload(db, current_user)


@router.get("/me/export")
@limiter.limit("3/hour")
def export_my_data(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Portable copy of everything held about this account (UU PDP art. 13).

    Rate limited because the query fans out across every user-owned table, and
    audited because a bulk personal-data read is exactly the event an incident
    investigation needs to see.
    """
    filename, body = render_export(db, user=current_user)
    record_audit_event_best_effort(
        user_id=current_user.id,
        event="account.data_exported",
        resource_type="account",
        resource_id=str(current_user.id),
    )
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("/me", status_code=status.HTTP_200_OK)
def delete_account(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Soft delete.

    Financial and audit records must survive account closure, so the row is
    tombstoned and the email is released for re-registration rather than the
    user being physically removed.
    """
    now = datetime.now(UTC)
    current_user.deleted_at = now
    current_user.is_active = False
    current_user.email = f"deleted+{current_user.id}@velora.invalid"
    db.commit()

    revoke_all_sessions(db, user_id=current_user.id, reason="account_deleted")
    record_audit_event_best_effort(user_id=current_user.id, event="auth.account_deleted")
    return {
        "status": "deleted",
        "retention_note": "Billing and audit records are retained as required by law.",
        "purge_after": (now + timedelta(days=30)).isoformat(),
    }


@router.get("/premium-only", response_model=UserResponse)
def premium_only(
    current_user=Depends(require_roles("pro", "max", "admin")), db: Session = Depends(get_db)
):
    return _user_payload(db, current_user)


@router.get("/admin-only", response_model=UserResponse)
def admin_only(current_user=Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return _user_payload(db, current_user)
