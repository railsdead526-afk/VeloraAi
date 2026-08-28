from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PaymentCreateRequest(BaseModel):
    plan: str = Field(pattern="^(pro|max)$")


class PaymentCreateResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    status: str = "pending"
    payment_provider: str = "midtrans"
    snap_token: Optional[str] = None
    redirect_url: Optional[str] = None
    manual_instructions: Optional[str] = None
    expires_at: Optional[datetime] = None
