"""Record scheduled maintenance executions.

The hourly job expires subscriptions, purges refresh tokens and cleans up
settled quota reservations. It runs outside the application, so a cron entry
that was never created looks exactly like one that runs cleanly - while paid
plans quietly never end.

This table makes the schedule observable: /ready reports the job as stale past
MAINTENANCE_MAX_AGE_MINUTES, and /metrics exposes its age as
velora_maintenance_age_seconds.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_maintenance_runs"
down_revision = "0017_subscription_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "maintenance_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=True),
    )
    op.create_index("ix_maintenance_runs_id", "maintenance_runs", ["id"])
    op.create_index("ix_maintenance_runs_job", "maintenance_runs", ["job"])
    op.create_index("ix_maintenance_runs_status", "maintenance_runs", ["status"])
    op.create_index("ix_maintenance_runs_finished_at", "maintenance_runs", ["finished_at"])


def downgrade() -> None:
    op.drop_index("ix_maintenance_runs_finished_at", table_name="maintenance_runs")
    op.drop_index("ix_maintenance_runs_status", table_name="maintenance_runs")
    op.drop_index("ix_maintenance_runs_job", table_name="maintenance_runs")
    op.drop_index("ix_maintenance_runs_id", table_name="maintenance_runs")
    op.drop_table("maintenance_runs")
