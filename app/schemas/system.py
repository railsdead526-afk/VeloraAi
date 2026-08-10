from pydantic import BaseModel


class MessageRequest(BaseModel):
    message: str


class GreetRequest(BaseModel):
    name: str
    message: str


class GreetResponse(BaseModel):
    reply: str
