"""Scheduled maintenance job.

Run every hour (cron, Railway cron, or Kubernetes CronJob):

    python -m scripts.run_maintenance

It is idempotent and safe to run concurrently with live traffic.
"""

from __future__ import annotations

import json
import logging
import sys

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.metrics import subscription_state
from app.core.observability import configure_logging
from app.models.billing import Subscription
from app.services.auth_tokens import purge_expired_tokens
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
    try:
        sweep = sweep_subscriptions(db)
        purged = purge_expired_tokens(db)
        gauges = refresh_subscription_gauges(db)
        report = {
            "event": "maintenance_completed",
            "subscriptions": sweep.as_dict(),
            "purged": purged,
            "subscription_counts": gauges,
        }
        logger.info(json.dumps(report, separators=(",", ":")))
        print(json.dumps(report, indent=2))
        return 0
    except Exception:
        logger.exception("maintenance job failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
