"""constrain supported user roles

Revision ID: 0004_user_role_constraint
Revises: 0003_integrity_indexes
"""
from alembic import op

revision = "0004_user_role_constraint"
down_revision = "0003_integrity_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('free', 'pro', 'max', 'admin')",
    )


def downgrade():
    op.drop_constraint("ck_users_role", "users", type_="check")
