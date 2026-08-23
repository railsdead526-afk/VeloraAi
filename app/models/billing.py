from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.types import UtcDateTime


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subscription_id", name="uq_subscription_provider_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    current_period_start: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True, index=True
    )
    #: End of the post-expiry grace window before the plan is downgraded.
    grace_until: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True, index=True)
    #: Smallest "days left" value already emailed for the current period.
    #: The sweep runs hourly, so without this marker every reminder went out
    #: once per hour for a whole day - 24 identical emails per milestone.
    #: Reset to NULL whenever the period is extended.
    last_reminder_days_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    canceled_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription", cascade="all, delete-orphan")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_order_id", name="uq_payment_provider_order"),
        UniqueConstraint(
            "provider", "provider_transaction_id", name="uq_payment_provider_transaction"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_order_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider_transaction_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    #: Opaque handle for a provider's embedded checkout widget, when it has
    #: one. Null for gateways that only offer a hosted redirect.
    checkout_token: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="IDR")
    plan: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    payment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: Sequential, human-readable invoice reference for accounting.
    invoice_number: Mapped[str | None] = mapped_column(
        String(40), nullable=True, unique=True, index=True
    )
    #: VAT/PPN component already included in `amount`.
    tax_amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    refund_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    refund_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    refund_transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="payments")
    subscription = relationship("Subscription", back_populates="payments")
