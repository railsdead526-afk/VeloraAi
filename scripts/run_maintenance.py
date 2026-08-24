"""Scheduled maintenance job.

Run every hour (cron, Railway cron, or Kubernetes CronJob):

    python -m scripts.run_maintenance

It is idempotent and safe to run concurrently with live traffic.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.metrics import subscription_state
from app.core.observability import configure_logging
from app.models.billing import Subscription
from app.services.auth_tokens import purge_expired_tokens
from app.services.maintenance_state import (
    STATUS_FAILED,
    STATUS_SUCCESS,
    purge_old_runs,
    record_run,
)
from app.services.quota_service import purge_settled_reservations
from app.services.subscription_lifecycle import sweep_subscriptions

logger = logging.getLogger("veloraai.maintenance")


def refresh_subscription_gauges(db) -> dict[str, int]:
    rows = db.execute(
        select(Subscription.plan, Subscription.status, func.count(Subscription.id)).group_by(
            Subscription.plan, Subscription.status
        )
    ).all()
    snapshot = {}
    for plan, status, count in rows:
        subscription_state.labels(plan, status).set(count)
        snapshot[f"{plan}:{status}"] = int(count)
    return snapshot


def main() -> int:
    configure_logging()
    db = SessionLocal()
    started_at = datetime.now(UTC)
    try:
        sweep = sweep_subscriptions(db)
        purged = purge_expired_tokens(db)
        purged["ai_request_reservations"] = purge_settled_reservations(db)
        purged["maintenance_runs"] = purge_old_runs(db)
        gauges = refresh_subscription_gauges(db)
        report = {
            "event": "maintenance_completed",
            "subscriptions": sweep.as_dict(),
            "purged": purged,
            "subscription_counts": gauges,
        }
        # Recorded so /ready and /metrics can tell whether the schedule is
        # actually firing. Without it, a cron entry that was never created is
        # indistinguishable from one that runs cleanly every hour.
        record_run(db, started_at=started_at, status=STATUS_SUCCESS, details=report)
        logger.info(json.dumps(report, separators=(",", ":")))
        print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:
        logger.exception("maintenance job failed")
        try:
            db.rollback()
            record_run(
                db,
                started_at=started_at,
                status=STATUS_FAILED,
                error_type=type(exc).__name__,
            )
        except Exception:
            logger.exception("could not record the maintenance failure")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
