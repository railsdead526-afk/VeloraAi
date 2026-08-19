from alembic import op
import sqlalchemy as sa

revision = "0010_payment_refund"
down_revision = "0009_payment_snap_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("refund_amount", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("payments", sa.Column("refund_status", sa.String(length=30), nullable=True))
    op.add_column("payments", sa.Column("refund_transaction_id", sa.String(length=255), nullable=True))
    op.add_column("payments", sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_payments_refund_transaction_id", "payments", ["refund_transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_refund_transaction_id", table_name="payments")
    op.drop_column("payments", "refunded_at")
    op.drop_column("payments", "refund_transaction_id")
    op.drop_column("payments", "refund_status")
    op.drop_column("payments", "refund_amount")
