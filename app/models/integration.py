from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.types import UtcDateTime

#: Providers a user can connect. Kept explicit so an unknown provider cannot be
#: written into the table by an API caller.
SUPPORTED_PROVIDERS = ("github", "vercel", "railway", "cloudflare", "supabase")


class UserIntegration(Base):
    """A third-party credential owned by a single user.

    The secret is stored only as AES-256-GCM ciphertext (see `app.core.crypto`)
    with the owning user and provider bound in as associated data, so a
    ciphertext cannot be replayed onto another user's row.
    """

    __tablename__ = "user_integrations"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_integration_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    secret_fingerprint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scopes: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="integrations")
