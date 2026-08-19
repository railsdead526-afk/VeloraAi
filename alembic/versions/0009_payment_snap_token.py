from alembic import op
import sqlalchemy as sa

revision = "0009_payment_snap_token"
down_revision = "0008_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("snap_token", sa.String(length=255), nullable=True))
    op.create_index("ix_payments_snap_token", "payments", ["snap_token"])


def downgrade() -> None:
    op.drop_index("ix_payments_snap_token", table_name="payments")
    op.drop_column("payments", "snap_token")
