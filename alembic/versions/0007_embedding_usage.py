from alembic import op
import sqlalchemy as sa

revision = "0007_embedding_usage"
down_revision = "0006_document_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "embedding_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="success"),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_embedding_usage_user_id", "embedding_usage", ["user_id"])
    op.create_index("ix_embedding_usage_document_id", "embedding_usage", ["document_id"])
    op.create_index("ix_embedding_usage_created_at", "embedding_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_embedding_usage_created_at", table_name="embedding_usage")
    op.drop_index("ix_embedding_usage_document_id", table_name="embedding_usage")
    op.drop_index("ix_embedding_usage_user_id", table_name="embedding_usage")
    op.drop_table("embedding_usage")
