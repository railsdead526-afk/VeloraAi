from fastapi import FastAPI

from app.api.v1 import auth, items, system
from app.core.database import Base, engine
from app.models.user import User
from app.models.item import Item

app = FastAPI(title="VeloraAi API")

Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"message": "Welcome to VeloraAi API"}


app.include_router(system.router, prefix="/api/v1")
app.include_router(items.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
