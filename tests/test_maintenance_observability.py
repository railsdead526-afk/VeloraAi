"""The scheduled maintenance job has to be observable.

It is where subscriptions expire, refresh tokens are purged and settled quota
reservations are cleaned up. It runs outside the application, so a cron entry
that was never created is indistinguishable from one firing cleanly every hour -
except that paid plans quietly never end. That is the revenue leak the
subscription lifecycle exists to prevent, reappearing as an operational gap.

These tests cover the job end to end and the freshness signals built on top of
it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.models.billing import Subscription
from app.models.maintenance import MaintenanceRun
from app.models.user import User
from app.services import maintenance_state
from app.services.maintenance_state import (
    STATUS_FAILED,
    STATUS_SUCCESS,
    last_successful_run,
    maintenance_health,
    purge_old_runs,
    record_run,
    seconds_since_last_success,
)


@pytest.fixture
def user(db):
    account = User(email="maintenance@example.com", hashed_password="hash", role="pro")
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


class TestRecording:
    def test_a_successful_run_is_recorded(self, db):
        started = datetime.now(UTC) - timedelta(seconds=2)
        run = record_run(db, started_at=started, status=STATUS_SUCCESS, details={"purged": 3})

        assert run.status == STATUS_SUCCESS
        assert run.duration_ms is not None and run.duration_ms >= 0
        assert json.loads(run.details) == {"purged": 3}
        assert run.error_type is None

    def test_a_failed_run_is_recorded_with_its_error_type(self, db):
        run = record_run(
            db,
            started_at=datetime.now(UTC),
            status=STATUS_FAILED,
            error_type="OperationalError",
        )
        assert run.status == STATUS_FAILED
        assert run.error_type == "OperationalError"

    def test_a_failed_run_does_not_count_as_success(self, db):
        record_run(db, started_at=datetime.now(UTC), status=STATUS_FAILED)
        assert last_successful_run(db) is None
        assert seconds_since_last_success(db) is None

    def test_the_latest_success_wins(self, db):
        record_run(db, started_at=datetime.now(UTC), status=STATUS_SUCCESS, details={"n": 1})
        second = record_run(
            db, started_at=datetime.now(UTC), status=STATUS_SUCCESS, details={"n": 2}
        )
        assert last_successful_run(db).id == second.id


class TestHealth:
    def test_never_run_is_unknown_not_error(self, db):
        """A fresh deployment must not fail readiness for a job it has yet to run."""
        health = maintenance_health(db)
        assert health["status"] == "unknown"
        assert health["status"] != "error"

    def test_a_recent_run_is_ok(self, db):
        record_run(db, started_at=datetime.now(UTC), status=STATUS_SUCCESS)
        assert maintenance_health(db)["status"] == "ok"

    def test_an_old_run_is_stale(self, db):
        run = record_run(db, started_at=datetime.now(UTC), status=STATUS_SUCCESS)
        run.finished_at = datetime.now(UTC) - timedelta(
            minutes=settings.maintenance_max_age_minutes + 30
        )
        db.commit()

        health = maintenance_health(db)
        assert health["status"] == "stale"
        assert health["age_seconds"] > health["max_age_seconds"]

    def test_stale_never_makes_readiness_fail(self, db):
        """Alert on it, do not take the service out of rotation for it."""
        run = record_run(db, started_at=datetime.now(UTC), status=STATUS_SUCCESS)
        run.finished_at = datetime.now(UTC) - timedelta(days=7)
        db.commit()

        assert maintenance_health(db)["status"] != "error"


class TestRetention:
    def test_old_runs_are_pruned_and_recent_ones_kept(self, db):
        old = record_run(db, started_at=datetime.now(UTC), status=STATUS_SUCCESS)
        old.finished_at = datetime.now(UTC) - maintenance_state.RUN_RETENTION - timedelta(days=1)
        db.commit()
        recent = record_run(db, started_at=datetime.now(UTC), status=STATUS_SUCCESS)
        old_id, recent_id = old.id, recent.id

        assert purge_old_runs(db) == 1

        # Read through a query rather than db.get: the deleted instance is still
        # in the identity map, and touching it raises instead of returning None.
        db.expire_all()
        remaining = {run.id for run in db.query(MaintenanceRun).all()}
        assert old_id not in remaining
        assert recent_id in remaining


class TestJobEndToEnd:
    def test_the_job_runs_and_records_itself(self, db, user, monkeypatch):
        """Drives scripts.run_maintenance.main against the test database."""
        import scripts.run_maintenance as job
        from app.core import database

        monkeypatch.setattr(job, "SessionLocal", lambda: database.SessionLocal())

        expired_start = datetime.now(UTC) - timedelta(days=60)
        db.add(
            Subscription(
                user_id=user.id,
                plan="pro",
                provider="midtrans",
                status="active",
                current_period_start=expired_start,
                current_period_end=expired_start + timedelta(days=30),
                grace_until=expired_start + timedelta(days=33),
            )
        )
        db.commit()

        assert job.main() == 0

        db.expire_all()
        run = last_successful_run(db)
        assert run is not None, "the job must record its own success"
        report = json.loads(run.details)
        assert report["event"] == "maintenance_completed"
        # The expired subscription was actually swept.
        assert report["subscriptions"]["expired"] == 1
        db.refresh(user)
        assert user.role == "free", "an expired subscription must downgrade the user"

    def test_a_failing_job_records_the_failure_and_exits_nonzero(self, db, monkeypatch):
        import scripts.run_maintenance as job
        from app.core import database

        monkeypatch.setattr(job, "SessionLocal", lambda: database.SessionLocal())

        def explode(*_args, **_kwargs):
            raise RuntimeError("database went away")

        monkeypatch.setattr(job, "sweep_subscriptions", explode)

        assert job.main() == 1

        db.expire_all()
        failures = db.query(MaintenanceRun).filter(MaintenanceRun.status == STATUS_FAILED).all()
        assert len(failures) == 1
        assert failures[0].error_type == "RuntimeError"
        # A failure must not look like a success to the freshness check.
        assert maintenance_health(db)["status"] == "unknown"
