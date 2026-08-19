from fastapi import APIRouter

from app.core.config import settings
from app.schemas.system import MessageRequest, GreetRequest, GreetResponse

router = APIRouter(tags=["System"])


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/info")
def app_info():
    return {
        "app_name": settings.app_name,
        "version": "0.1.1",
        "environment": settings.app_env,
        "ai_provider": settings.ai_provider,
    }


@router.get("/hello/{name}")
def say_hello(name: str):
    return {"message": f"Hello, {name}!"}


@router.post("/echo")
def echo_message(payload: MessageRequest):
    return {"you_sent": payload.message}


@router.post("/greet", response_model=GreetResponse)
def greet_user(payload: GreetRequest):
    return {"reply": f"Halo {payload.name}, kamu bilang: {payload.message}"}


@router.get("/search")
def search(q: str | None = None, limit: int = 10):
    safe_limit = max(1, min(limit, 50))
    return {"query": q, "limit": safe_limit, "results": []}
