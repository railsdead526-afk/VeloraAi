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

_NAMING_CONVENTION = {"fk": "%(table_name)s_%(column_0_name)s_fkey"}


def upgrade():
    # Batch mode rebuilds SQLite tables when ALTER CONSTRAINT is unsupported;
    # on PostgreSQL it uses the native ALTER operations.
    with op.batch_alter_table("conversations", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("conversations_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "conversations_user_id_fkey",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("messages", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("messages_conversation_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "messages_conversation_id_fkey",
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_check_constraint(
            "ck_messages_role",
            "role IN ('user', 'assistant', 'system')",
        )

    with op.batch_alter_table("ai_usage", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("ai_usage_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "ai_usage_user_id_fkey",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.drop_constraint("ai_usage_conversation_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "ai_usage_conversation_id_fkey",
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_check_constraint(
            "ck_ai_usage_tokens_nonnegative",
            "input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0",
        )

    op.create_index("ix_conversations_user_created", "conversations", ["user_id", "created_at"])
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])
    op.create_index("ix_ai_usage_user_created", "ai_usage", ["user_id", "created_at"])


def downgrade():
    op.drop_index("ix_ai_usage_user_created", table_name="ai_usage")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_index("ix_conversations_user_created", table_name="conversations")

    with op.batch_alter_table("ai_usage", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("ck_ai_usage_tokens_nonnegative", type_="check")
        batch_op.drop_constraint("ai_usage_conversation_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("ai_usage_conversation_id_fkey", "conversations", ["conversation_id"], ["id"])
        batch_op.drop_constraint("ai_usage_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("ai_usage_user_id_fkey", "users", ["user_id"], ["id"])

    with op.batch_alter_table("messages", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("ck_messages_role", type_="check")
        batch_op.drop_constraint("messages_conversation_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("messages_conversation_id_fkey", "conversations", ["conversation_id"], ["id"])

    with op.batch_alter_table("conversations", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("conversations_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("conversations_user_id_fkey", "users", ["user_id"], ["id"])
