from pydantic import BaseModel, Field


class PaymentCreateRequest(BaseModel):
    plan: str = Field(pattern="^(pro|max)$")


class PaymentCreateResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    checkout_token: str | None = None
    redirect_url: str
