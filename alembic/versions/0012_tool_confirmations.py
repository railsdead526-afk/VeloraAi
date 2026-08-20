from alembic import op
import sqlalchemy as sa

revision = "0012_tool_confirmations"
down_revision = "0011_rag_index_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_confirmations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_tool_confirmations_token_hash"),
    )
    op.create_index("ix_tool_confirmations_token_hash", "tool_confirmations", ["token_hash"])
    op.create_index("ix_tool_confirmations_lookup", "tool_confirmations", ["token_hash", "used_at"])
    op.create_index("ix_tool_confirmations_expiry", "tool_confirmations", ["expires_at"])
    op.create_index("ix_tool_confirmations_user_id", "tool_confirmations", ["user_id"])
    op.create_index("ix_tool_confirmations_conversation_id", "tool_confirmations", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_confirmations_conversation_id", table_name="tool_confirmations")
    op.drop_index("ix_tool_confirmations_user_id", table_name="tool_confirmations")
    op.drop_index("ix_tool_confirmations_expiry", table_name="tool_confirmations")
    op.drop_index("ix_tool_confirmations_lookup", table_name="tool_confirmations")
    op.drop_index("ix_tool_confirmations_token_hash", table_name="tool_confirmations")
    op.drop_table("tool_confirmations")
