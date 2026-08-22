from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password
from app.models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    """Look up an active (non-tombstoned) account by email."""
    return db.query(User).filter(User.email == email, User.deleted_at.is_(None)).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    user = db.get(User, user_id)
    return None if user is None or user.is_deleted else user


def create_user(db: Session, email: str, password: str) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        role="free",
        password_changed_at=datetime.now(UTC),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user or not user.is_active or user.is_deleted:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
