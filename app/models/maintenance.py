"""Record of scheduled maintenance executions.

The hourly job is where subscriptions expire, refresh tokens are purged and
settled quota reservations are cleaned up. None of that is visible from the
application: if the cron entry is never created, or silently stops, everything
keeps serving traffic while paid plans quietly never end.

That is exactly the revenue leak the subscription lifecycle was built to close,
so the job not running has to be observable rather than assumed.
"""

from datetime import datetime

from sqlalchemy import Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import UtcDateTime

JOB_MAINTENANCE = "maintenance"

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


class MaintenanceRun(Base):
    """One execution of a scheduled job, successful or not."""

    __tablename__ = "maintenance_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    finished_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False, index=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: JSON summary of what the run did, for support and debugging.
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
