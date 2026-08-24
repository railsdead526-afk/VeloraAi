"""Rename payments.snap_token to checkout_token.

"Snap" is Midtrans's name for its checkout widget. With payments behind a
provider abstraction, one vendor's vocabulary should not be baked into the
schema or the public API.
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_neutral_checkout_token"
down_revision = "0015_company_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_payments_snap_token", table_name="payments")
    op.alter_column("payments", "snap_token", new_column_name="checkout_token")
    op.create_index("ix_payments_checkout_token", "payments", ["checkout_token"])


def downgrade() -> None:
    op.drop_index("ix_payments_checkout_token", table_name="payments")
    op.alter_column("payments", "checkout_token", new_column_name="snap_token")
    op.create_index("ix_payments_snap_token", "payments", ["snap_token"])
