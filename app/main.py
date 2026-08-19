from fastapi import FastAPI

from app.api.v1 import auth, system, conversations

app = FastAPI(title="VeloraAi API")


@app.get("/")
def root():
    return {"message": "Welcome to VeloraAi API"}


app.include_router(conversations.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
