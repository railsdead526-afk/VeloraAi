from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=12000)
    confirm_tools: bool = False
    tool_confirmation_token: str | None = None
    use_rag: bool = True

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message content cannot be blank")
        return value


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime


class ChatReplyResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
