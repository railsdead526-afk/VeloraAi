from pydantic import BaseModel, Field


class PaymentCreateRequest(BaseModel):
    plan: str = Field(pattern="^(pro|max)$")


class PaymentCreateResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    checkout_token: str | None = None
    redirect_url: str


class RefundRequest(BaseModel):
    """Admin-initiated refund.

    `amount` is in the smallest currency unit, matching `Payment.amount`.
    Omitting it refunds everything still outstanding, which is the common case
    and what the endpoint did before partial refunds existed.
    """

    amount: int | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, max_length=255)


class RefundResponse(BaseModel):
    status: str
    payment_id: int
    #: Amount moved by this call.
    refund_amount: int
    #: Total refunded across every call against this payment.
    refunded_total: int
    #: What is still refundable.
    remaining: int
    fully_refunded: bool
