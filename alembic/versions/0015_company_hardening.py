"""Company-readiness hardening.

Adds:
  * per-user encrypted third-party credentials (`user_integrations`)
  * revocable sessions (`refresh_tokens`, `revoked_access_tokens`)
  * email verification / password reset (`user_verification_tokens`)
  * login lockout telemetry (`login_attempts`)
  * user lifecycle columns (verification, lockout, soft delete, timestamps)
  * subscription lifecycle + invoicing columns
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_company_hardening"
down_revision = "0014_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------- users --
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    # -------------------------------------------------------- integrations --
    op.create_table(
        "user_integrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_fingerprint", sa.String(length=16), nullable=True),
        sa.Column("scopes", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_integration_provider"),
    )
    op.create_index("ix_user_integrations_user_id", "user_integrations", ["user_id"])
    op.create_index("ix_user_integrations_provider", "user_integrations", ["provider"])
    op.create_index("ix_user_integrations_status", "user_integrations", ["status"])

    # ------------------------------------------------------------ sessions --
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
        sa.Column("replaced_by_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])

    op.create_table(
        "revoked_access_tokens",
        sa.Column("jti", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_revoked_access_tokens_user_id", "revoked_access_tokens", ["user_id"])
    op.create_index("ix_revoked_access_tokens_expires_at", "revoked_access_tokens", ["expires_at"])

    # ------------------------------------------------------- verification ---
    op.create_table(
        "user_verification_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_user_verification_tokens_hash"),
    )
    op.create_index("ix_user_verification_tokens_user_id", "user_verification_tokens", ["user_id"])
    op.create_index("ix_user_verification_tokens_token_hash", "user_verification_tokens", ["token_hash"])
    op.create_index("ix_user_verification_tokens_expires_at", "user_verification_tokens", ["expires_at"])
    op.create_index(
        "ix_user_verification_tokens_user_purpose", "user_verification_tokens", ["user_id", "purpose"]
    )

    # ------------------------------------------------------ login attempts --
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("successful", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_login_attempts_email_created", "login_attempts", ["email_hash", "created_at"])
    op.create_index("ix_login_attempts_ip_created", "login_attempts", ["ip_hash", "created_at"])

    # -------------------------------------------------- billing lifecycle ---
    op.add_column("subscriptions", sa.Column("grace_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "subscriptions",
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_subscriptions_current_period_end", "subscriptions", ["current_period_end"])
    op.create_index("ix_subscriptions_grace_until", "subscriptions", ["grace_until"])

    op.add_column("payments", sa.Column("invoice_number", sa.String(length=40), nullable=True))
    op.add_column(
        "payments", sa.Column("tax_amount", sa.BigInteger(), nullable=False, server_default="0")
    )
    op.create_index("ix_payments_invoice_number", "payments", ["invoice_number"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_payments_invoice_number", table_name="payments")
    op.drop_column("payments", "tax_amount")
    op.drop_column("payments", "invoice_number")

    op.drop_index("ix_subscriptions_grace_until", table_name="subscriptions")
    op.drop_index("ix_subscriptions_current_period_end", table_name="subscriptions")
    op.drop_column("subscriptions", "cancel_at_period_end")
    op.drop_column("subscriptions", "grace_until")

    op.drop_index("ix_login_attempts_ip_created", table_name="login_attempts")
    op.drop_index("ix_login_attempts_email_created", table_name="login_attempts")
    op.drop_table("login_attempts")

    op.drop_index("ix_user_verification_tokens_user_purpose", table_name="user_verification_tokens")
    op.drop_index("ix_user_verification_tokens_expires_at", table_name="user_verification_tokens")
    op.drop_index("ix_user_verification_tokens_token_hash", table_name="user_verification_tokens")
    op.drop_index("ix_user_verification_tokens_user_id", table_name="user_verification_tokens")
    op.drop_table("user_verification_tokens")

    op.drop_index("ix_revoked_access_tokens_expires_at", table_name="revoked_access_tokens")
    op.drop_index("ix_revoked_access_tokens_user_id", table_name="revoked_access_tokens")
    op.drop_table("revoked_access_tokens")

    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_user_integrations_status", table_name="user_integrations")
    op.drop_index("ix_user_integrations_provider", table_name="user_integrations")
    op.drop_index("ix_user_integrations_user_id", table_name="user_integrations")
    op.drop_table("user_integrations")

    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "created_at")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "email_verified_at")
