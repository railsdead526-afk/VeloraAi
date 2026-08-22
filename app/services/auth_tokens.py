"""Session, revocation, verification, and lockout logic.

Access tokens are short-lived JWTs; refresh tokens are opaque, stored hashed,
and rotate on every use. Reusing an already-rotated refresh token is treated as
theft and revokes the whole family for that user.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    generate_opaque_token,
    hash_opaque_token,
)
from app.models.auth import (
    LoginAttempt,
    RefreshToken,
    RevokedAccessToken,
    UserVerificationToken,
)
from app.models.user import User

PURPOSE_EMAIL_VERIFICATION = "email_verification"
PURPOSE_PASSWORD_RESET = "password_reset"  # noqa: S105 - an enum value, not a secret


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; normalise before comparing."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _pepper(value: str) -> str:
    """Salted digest for privacy-sensitive identifiers (email, IP)."""
    return hashlib.sha256(f"{settings.secret_key}|{value.lower().strip()}".encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Refresh tokens
# --------------------------------------------------------------------------- #


def issue_refresh_token(
    db: Session,
    *,
    user_id: int,
    user_agent: str | None = None,
    ip: str | None = None,
    commit: bool = True,
) -> str:
    """Create a new session and return the plaintext token (shown once)."""
    token = generate_opaque_token()
    record = RefreshToken(
        user_id=user_id,
        token_hash=hash_opaque_token(token),
        expires_at=_now() + timedelta(days=settings.refresh_token_expire_days),
        user_agent=(user_agent or "")[:255] or None,
        ip_hash=_pepper(ip) if ip else None,
    )
    db.add(record)
    db.flush()
    _enforce_session_cap(db, user_id=user_id, keep_id=record.id)
    if commit:
        db.commit()
    return token


def _enforce_session_cap(db: Session, *, user_id: int, keep_id: int) -> None:
    """Revoke the oldest sessions beyond `MAX_ACTIVE_SESSIONS`.

    Ordering is by primary key, not `issued_at`: several sessions can share the
    same timestamp at second resolution, which makes timestamp ordering
    non-deterministic and lets the cap silently under-enforce.
    """
    active = list(
        db.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > _now(),
            )
            .order_by(RefreshToken.id.desc())
        ).scalars()
    )
    for stale in active[settings.max_active_sessions :]:
        if stale.id == keep_id:
            continue
        stale.revoked_at = _now()
        stale.revoked_reason = "session_cap"


def get_active_refresh_token(db: Session, token: str) -> RefreshToken | None:
    record = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_opaque_token(token))
    ).scalar_one_or_none()
    if record is None:
        return None
    if record.revoked_at is not None:
        return None
    if (_as_aware(record.expires_at) or _now()) <= _now():
        return None
    return record


def rotate_refresh_token(
    db: Session,
    *,
    token: str,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[User, str] | None:
    """Consume `token` and issue its replacement.

    Returns `None` when the token is unknown, expired, or already revoked. If a
    *revoked* token is replayed, every session for that user is torn down.
    """
    token_hash = hash_opaque_token(token)
    record = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if record is None:
        return None

    if record.revoked_at is not None:
        # Replay of a rotated token: assume compromise, drop the whole family.
        revoke_all_sessions(db, user_id=record.user_id, reason="reuse_detected")
        return None

    if (_as_aware(record.expires_at) or _now()) <= _now():
        return None

    user = db.get(User, record.user_id)
    if user is None or not user.is_active or user.is_deleted:
        return None

    replacement = generate_opaque_token()
    record.revoked_at = _now()
    record.revoked_reason = "rotated"
    record.replaced_by_hash = hash_opaque_token(replacement)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=record.replaced_by_hash,
            expires_at=_now() + timedelta(days=settings.refresh_token_expire_days),
            user_agent=(user_agent or record.user_agent or "")[:255] or None,
            ip_hash=_pepper(ip) if ip else record.ip_hash,
        )
    )
    db.commit()
    return user, replacement


def revoke_refresh_token(db: Session, *, token: str, reason: str = "logout") -> bool:
    record = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_opaque_token(token))
    ).scalar_one_or_none()
    if record is None or record.revoked_at is not None:
        return False
    record.revoked_at = _now()
    record.revoked_reason = reason
    db.commit()
    return True


def revoke_all_sessions(db: Session, *, user_id: int, reason: str = "logout_all") -> int:
    count = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .update(
            {RefreshToken.revoked_at: _now(), RefreshToken.revoked_reason: reason},
            synchronize_session=False,
        )
    )
    db.commit()
    return int(count or 0)


def list_sessions(db: Session, *, user_id: int) -> list[RefreshToken]:
    return list(
        db.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > _now(),
            )
            .order_by(RefreshToken.id.desc())
        ).scalars()
    )


# --------------------------------------------------------------------------- #
# Access token revocation
# --------------------------------------------------------------------------- #


def revoke_access_token(
    db: Session, *, jti: str, user_id: int | None, expires_at: datetime, reason: str = "logout"
) -> None:
    if not jti:
        return
    if db.get(RevokedAccessToken, jti) is not None:
        return
    db.add(
        RevokedAccessToken(
            jti=jti,
            user_id=user_id,
            expires_at=expires_at,
            reason=reason[:64],
        )
    )
    db.commit()


def is_access_token_revoked(db: Session, *, jti: str) -> bool:
    if not jti:
        return False
    return db.get(RevokedAccessToken, jti) is not None


def purge_expired_tokens(db: Session) -> dict[str, int]:
    """Housekeeping for the scheduled maintenance job."""
    now = _now()
    revoked = (
        db.query(RevokedAccessToken)
        .filter(RevokedAccessToken.expires_at < now)
        .delete(synchronize_session=False)
    )
    refresh = (
        db.query(RefreshToken)
        .filter(RefreshToken.expires_at < now - timedelta(days=30))
        .delete(synchronize_session=False)
    )
    verification = (
        db.query(UserVerificationToken)
        .filter(UserVerificationToken.expires_at < now - timedelta(days=7))
        .delete(synchronize_session=False)
    )
    attempts = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.created_at < now - timedelta(days=90))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {
        "revoked_access_tokens": int(revoked or 0),
        "refresh_tokens": int(refresh or 0),
        "verification_tokens": int(verification or 0),
        "login_attempts": int(attempts or 0),
    }


# --------------------------------------------------------------------------- #
# Verification / password reset tokens
# --------------------------------------------------------------------------- #


def issue_verification_token(db: Session, *, user_id: int, purpose: str) -> str:
    """Invalidate outstanding tokens for `purpose` and issue a fresh one."""
    db.query(UserVerificationToken).filter(
        UserVerificationToken.user_id == user_id,
        UserVerificationToken.purpose == purpose,
        UserVerificationToken.used_at.is_(None),
    ).update({UserVerificationToken.used_at: _now()}, synchronize_session=False)

    ttl = (
        timedelta(minutes=settings.password_reset_ttl_minutes)
        if purpose == PURPOSE_PASSWORD_RESET
        else timedelta(hours=settings.email_verification_ttl_hours)
    )
    token = generate_opaque_token(32)
    db.add(
        UserVerificationToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_opaque_token(token),
            expires_at=_now() + ttl,
        )
    )
    db.commit()
    return token


def consume_verification_token(db: Session, *, token: str, purpose: str) -> User | None:
    record = db.execute(
        select(UserVerificationToken).where(
            UserVerificationToken.token_hash == hash_opaque_token(token),
            UserVerificationToken.purpose == purpose,
        )
    ).scalar_one_or_none()

    if record is None or record.used_at is not None:
        return None
    if (_as_aware(record.expires_at) or _now()) <= _now():
        return None

    user = db.get(User, record.user_id)
    if user is None or user.is_deleted:
        return None

    record.used_at = _now()
    db.commit()
    return user


# --------------------------------------------------------------------------- #
# Login throttling
# --------------------------------------------------------------------------- #


def record_login_attempt(db: Session, *, email: str, ip: str | None, successful: bool) -> None:
    db.add(
        LoginAttempt(
            email_hash=_pepper(email),
            ip_hash=_pepper(ip) if ip else None,
            successful=successful,
        )
    )
    db.commit()


def recent_failed_attempts(db: Session, *, email: str, minutes: int | None = None) -> int:
    window = timedelta(minutes=minutes or settings.login_lockout_minutes)
    total = db.execute(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.email_hash == _pepper(email),
            LoginAttempt.successful.is_(False),
            LoginAttempt.created_at >= _now() - window,
        )
    ).scalar()
    return int(total or 0)


def is_locked_out(db: Session, *, email: str) -> bool:
    return recent_failed_attempts(db, email=email) >= settings.login_max_failed_attempts


def clear_failed_attempts(db: Session, *, email: str) -> None:
    db.query(LoginAttempt).filter(
        LoginAttempt.email_hash == _pepper(email),
        LoginAttempt.successful.is_(False),
    ).delete(synchronize_session=False)
    db.commit()
