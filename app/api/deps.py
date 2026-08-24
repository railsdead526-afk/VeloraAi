import hmac

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.api.auth_cookies import ACCESS_TOKEN_COOKIE, CSRF_COOKIE
from app.core.database import get_db
from app.core.security import decode_access_token
from app.crud.user import get_user_by_email

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: str | None = Depends(oauth2_scheme),
    cookie_token: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = bearer_token or cookie_token
    if not token:
        raise credentials_exception

    if cookie_token and not bearer_token and request.method in _UNSAFE_METHODS:
        expected_csrf = request.cookies.get(CSRF_COOKIE)
        if not expected_csrf or not csrf_token or not hmac.compare_digest(expected_csrf, csrf_token):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")

    try:
        payload = decode_access_token(token)
        email = payload.get("sub")
        if email is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        raise credentials_exception

    return user


def require_roles(*allowed_roles: str):
    def role_checker(current_user=Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return current_user

    return role_checker
