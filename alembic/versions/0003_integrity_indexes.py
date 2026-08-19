"""enforce relational integrity and query indexes

Revision ID: 0003_integrity_indexes
Revises: 0002_ai_usage
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_integrity_indexes"
down_revision = "0002_ai_usage"
branch_labels = None
depends_on = None


def upgrade():
    # Recreate foreign keys with database-level cascade semantics.
    op.drop_constraint("conversations_user_id_fkey", "conversations", type_="foreignkey")
    op.create_foreign_key(
        "conversations_user_id_fkey",
        "conversations",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("messages_conversation_id_fkey", "messages", type_="foreignkey")
    op.create_foreign_key(
        "messages_conversation_id_fkey",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("ai_usage_user_id_fkey", "ai_usage", type_="foreignkey")
    op.create_foreign_key(
        "ai_usage_user_id_fkey",
        "ai_usage",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("ai_usage_conversation_id_fkey", "ai_usage", type_="foreignkey")
    op.create_foreign_key(
        "ai_usage_conversation_id_fkey",
        "ai_usage",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index("ix_conversations_user_created", "conversations", ["user_id", "created_at"])
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])
    op.create_index("ix_ai_usage_user_created", "ai_usage", ["user_id", "created_at"])

    op.create_check_constraint(
        "ck_messages_role",
        "messages",
        "role IN ('user', 'assistant', 'system')",
    )
    op.create_check_constraint(
        "ck_ai_usage_tokens_nonnegative",
        "ai_usage",
        "input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0",
    )


def downgrade():
    op.drop_constraint("ck_ai_usage_tokens_nonnegative", "ai_usage", type_="check")
    op.drop_constraint("ck_messages_role", "messages", type_="check")
    op.drop_index("ix_ai_usage_user_created", table_name="ai_usage")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_index("ix_conversations_user_created", table_name="conversations")

    op.drop_constraint("ai_usage_conversation_id_fkey", "ai_usage", type_="foreignkey")
    op.create_foreign_key("ai_usage_conversation_id_fkey", "ai_usage", "conversations", ["conversation_id"], ["id"])
    op.drop_constraint("ai_usage_user_id_fkey", "ai_usage", type_="foreignkey")
    op.create_foreign_key("ai_usage_user_id_fkey", "ai_usage", "users", ["user_id"], ["id"])
    op.drop_constraint("messages_conversation_id_fkey", "messages", type_="foreignkey")
    op.create_foreign_key("messages_conversation_id_fkey", "messages", "conversations", ["conversation_id"], ["id"])
    op.drop_constraint("conversations_user_id_fkey", "conversations", type_="foreignkey")
    op.create_foreign_key("conversations_user_id_fkey", "conversations", "users", ["user_id"], ["id"])
