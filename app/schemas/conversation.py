from datetime import datetime

from pydantic import BaseModel, Field, validator


class ConversationCreate(BaseModel):
    title: str | None = Field(default="New Chat", max_length=120)

    @validator("title")
    def normalize_title(cls, value):
        if value is None:
            return "New Chat"
        value = value.strip()
        return value or "New Chat"


class ConversationUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)

    @validator("title")
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Conversation title cannot be blank")
        return value


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime

    class Config:
        orm_mode = True
