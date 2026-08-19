"""add ai usage tracking

Revision ID: 0002_ai_usage
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_ai_usage"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
    )
    op.create_index("ix_ai_usage_id", "ai_usage", ["id"], unique=False)
    op.create_index("ix_ai_usage_user_id", "ai_usage", ["user_id"], unique=False)
    op.create_index("ix_ai_usage_conversation_id", "ai_usage", ["conversation_id"], unique=False)


def downgrade():
    op.drop_index("ix_ai_usage_conversation_id", table_name="ai_usage")
    op.drop_index("ix_ai_usage_user_id", table_name="ai_usage")
    op.drop_index("ix_ai_usage_id", table_name="ai_usage")
    op.drop_table("ai_usage")
