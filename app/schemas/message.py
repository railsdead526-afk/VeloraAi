from datetime import datetime
from pydantic import BaseModel


class MessageCreate(BaseModel):
    content: str


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

