"""Bookkeeping and freshness checks for the scheduled maintenance job.

The job carries real business consequences - it is what expires subscriptions -
but it runs outside the application, so nothing notices when it stops. These
helpers record every run and let `/ready` and `/metrics` report how long it has
been since the last successful one.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.maintenance import (
    JOB_MAINTENANCE,
    STATUS_FAILED,
    STATUS_SUCCESS,
    MaintenanceRun,
)

#: Runs older than this are pruned; a few days is enough to debug an incident.
RUN_RETENTION = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(UTC)


def record_run(
    db: Session,
    *,
    started_at: datetime,
    status: str,
    details: dict[str, Any] | None = None,
    error_type: str | None = None,
    job: str = JOB_MAINTENANCE,
) -> MaintenanceRun:
    finished_at = _now()
    run = MaintenanceRun(
        job=job,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=int((finished_at - started_at).total_seconds() * 1000),
        details=json.dumps(details, separators=(",", ":")) if details else None,
        error_type=error_type,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def last_successful_run(db: Session, *, job: str = JOB_MAINTENANCE) -> MaintenanceRun | None:
    return db.execute(
        select(MaintenanceRun)
        .where(MaintenanceRun.job == job, MaintenanceRun.status == STATUS_SUCCESS)
        .order_by(MaintenanceRun.finished_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def seconds_since_last_success(
    db: Session, *, job: str = JOB_MAINTENANCE, now: datetime | None = None
) -> float | None:
    """Age of the last successful run, or None if it has never succeeded."""
    run = last_successful_run(db, job=job)
    if run is None:
        return None
    return max(0.0, ((now or _now()) - run.finished_at).total_seconds())


def maintenance_health(
    db: Session, *, job: str = JOB_MAINTENANCE, now: datetime | None = None
) -> dict[str, Any]:
    """Freshness of the scheduled job, shaped for the readiness payload.

    Deliberately never reports ``error``. A brand-new deployment has legitimately
    never run the job, and failing readiness there would block the very deploy
    that installs the schedule. ``stale`` is loud enough to alert on without
    taking the service out of rotation.
    """
    age = seconds_since_last_success(db, job=job, now=now)
    max_age = settings.maintenance_max_age_minutes * 60

    if age is None:
        return {
            "status": "unknown",
            "detail": "the maintenance job has never completed successfully",
            "max_age_seconds": max_age,
        }

    return {
        "status": "ok" if age <= max_age else "stale",
        "age_seconds": int(age),
        "max_age_seconds": max_age,
    }


def purge_old_runs(db: Session, *, now: datetime | None = None) -> int:
    cutoff = (now or _now()) - RUN_RETENTION
    deleted = (
        db.query(MaintenanceRun)
        .filter(MaintenanceRun.finished_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(deleted or 0)


__all__ = [
    "STATUS_FAILED",
    "STATUS_SUCCESS",
    "last_successful_run",
    "maintenance_health",
    "purge_old_runs",
    "record_run",
    "seconds_since_last_success",
]
