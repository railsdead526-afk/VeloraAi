from alembic import op
import sqlalchemy as sa

revision = "0013_ai_request_reservations"
down_revision = "0012_tool_confirmations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_request_reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="reserved"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_request_reservations_user_id", "ai_request_reservations", ["user_id"])
    op.create_index("ix_ai_request_reservations_status", "ai_request_reservations", ["status"])
    op.create_index("ix_ai_request_reservations_expires_at", "ai_request_reservations", ["expires_at"])
    op.create_check_constraint(
        "ck_ai_request_reservations_status",
        "ai_request_reservations",
        "status IN ('reserved', 'completed', 'released')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ai_request_reservations_status", "ai_request_reservations", type_="check")
    op.drop_index("ix_ai_request_reservations_expires_at", table_name="ai_request_reservations")
    op.drop_index("ix_ai_request_reservations_status", table_name="ai_request_reservations")
    op.drop_index("ix_ai_request_reservations_user_id", table_name="ai_request_reservations")
    op.drop_table("ai_request_reservations")
