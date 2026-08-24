from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import UtcDateTime


class AIRequestReservation(Base):
    __tablename__ = "ai_request_reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved")
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
