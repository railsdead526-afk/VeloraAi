from pydantic import BaseModel, Field


class MessageRequest(BaseModel):
    message: str = Field(..., min_length=3)


class GreetRequest(BaseModel):
    name: str = Field(..., min_length=2)
    message: str = Field(..., min_length=3)


class GreetResponse(BaseModel):
    reply: str

