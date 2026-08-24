from pydantic import BaseModel, Field


class PaymentConfigResponse(BaseModel):
    """Non-secret checkout settings for the UI.

    The shape is shared by every provider so the client renders one honest
    state per mode. When payments are disabled, pricing keys are ``None`` and
    ``reason`` explains why, which is exactly what a deployment that is not
    selling anything yet (the default) should show instead of a dead checkout.
    """

    provider: str
    enabled: bool = True
    is_production: bool | None = None
    pro_price_idr: int | None = None
    max_price_idr: int | None = None
    reason: str | None = None


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
