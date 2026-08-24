"""constrain supported user roles

Revision ID: 0004_user_role_constraint
Revises: 0003_integrity_indexes
"""

from alembic import op


revision = "0004_user_role_constraint"
down_revision = "0003_integrity_indexes"
branch_labels = None
depends_on = None


_NAMING_CONVENTION = {"ck": "ck_%(table_name)s_%(constraint_name)s"}


def upgrade():
    with op.batch_alter_table("users", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.create_check_constraint(
            "ck_users_role",
            "role IN ('free', 'pro', 'max', 'admin')",
        )


def downgrade():
    with op.batch_alter_table("users", naming_convention=_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("ck_users_role", type_="check")
