from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subscription_id", name="uq_subscription_provider_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan = Column(String(20), nullable=False)
    provider = Column(String(30), nullable=False)
    provider_subscription_id = Column(String(255), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription", cascade="all, delete-orphan")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_order_id", name="uq_payment_provider_order"),
        UniqueConstraint("provider", "provider_transaction_id", name="uq_payment_provider_transaction"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(30), nullable=False)
    provider_order_id = Column(String(255), nullable=False, index=True)
    provider_transaction_id = Column(String(255), nullable=True, index=True)
    amount = Column(BigInteger, nullable=False)
    currency = Column(String(10), nullable=False, default="IDR")
    plan = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False, default="pending", index=True)
    payment_type = Column(String(50), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="payments")
    subscription = relationship("Subscription", back_populates="payments")
