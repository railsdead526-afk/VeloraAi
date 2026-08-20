from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    role: str
    daily_requests_used: int = 0
    daily_request_limit: int | None = None
    daily_reset_at: datetime | None = None

    class Config:
        orm_mode = True
