from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import TokenError, decode_access_token
from app.crud.user import get_user_by_email
from app.models.user import User
from app.services.auth_tokens import is_access_token_revoked

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> User:
    try:
        payload = decode_access_token(token)
    except TokenError:
        raise _CREDENTIALS_EXCEPTION from None

    email = payload.get("sub")
    if not email:
        raise _CREDENTIALS_EXCEPTION

    jti = payload.get("jti", "")
    if jti and is_access_token_revoked(db, jti=jti):
        raise _CREDENTIALS_EXCEPTION

    user = get_user_by_email(db, email)
    if user is None or not user.is_active or user.is_deleted:
        raise _CREDENTIALS_EXCEPTION

    return user


def get_verified_user(current_user: User = Depends(get_current_user)) -> User:
    """Require a confirmed email address when verification is enforced."""
    if settings.require_email_verification and not current_user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address must be verified before using this resource",
        )
    return current_user


def require_roles(*allowed_roles: str):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return current_user

    return role_checker


def client_ip(request: Request) -> str | None:
    """Best-effort client address.

    `X-Forwarded-For` is only trusted when the deployment declares trusted
    hosts, because otherwise a client can forge it to dodge lockout.
    """
    if settings.trusted_hosts:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
