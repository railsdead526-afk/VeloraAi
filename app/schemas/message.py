from datetime import datetime

from pydantic import BaseModel, Field, validator


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=12000)
    confirm_tools: bool = False

    @validator("content")
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message content cannot be blank")
        return value


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


class ChatReplyResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
