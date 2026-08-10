from fastapi import FastAPI

from app.api.v1 import auth, system, conversations
from app.core.database import Base, engine
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message

app = FastAPI(title="VeloraAi API")

Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"message": "Welcome to VeloraAi API"}


app.include_router(conversations.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
