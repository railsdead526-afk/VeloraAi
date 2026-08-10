from datetime import datetime
from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str | None = "New Chat"


class ConversationUpdate(BaseModel):
    title: str


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime

    class Config:
        orm_mode = True

