from alembic import op
import sqlalchemy as sa

revision = "0011_rag_index_recovery"
down_revision = "0010_payment_refund"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("indexing_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("last_index_error", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "last_indexed_at")
    op.drop_column("documents", "last_index_error")
    op.drop_column("documents", "indexing_attempts")
