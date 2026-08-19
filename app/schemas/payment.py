from pydantic import BaseModel, Field


class PaymentCreateRequest(BaseModel):
    plan: str = Field(pattern="^(pro|max)$")


class PaymentCreateResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    snap_token: str
    redirect_url: str
