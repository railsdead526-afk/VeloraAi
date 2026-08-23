"""Track which renewal reminder has already been sent.

The lifecycle sweep runs hourly and decided whether to email a reminder from
`(period_end - now).days`, which stays on the same value for a whole day. Every
milestone therefore went out 24 times: 72 identical emails per subscription per
period. Besides being unpleasant, that damages sender reputation, which puts
the emails that matter - verification and password reset - into spam folders.

This column records the smallest "days left" milestone already emailed for the
current period. It is reset to NULL whenever the period is extended.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_subscription_reminders"
down_revision = "0016_neutral_checkout_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("last_reminder_days_left", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "last_reminder_days_left")
