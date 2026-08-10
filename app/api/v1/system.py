from fastapi import APIRouter
from app.schemas.system import MessageRequest, GreetRequest, GreetResponse

router = APIRouter(tags=["System"])


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "VeloraAi"
    }


@router.get("/info")
def app_info():
    return {
        "app_name": "VeloraAi",
        "version": "0.1.0",
        "environment": "development"
    }


@router.get("/hello/{name}")
def say_hello(name: str):
    return {
        "message": f"Hello, {name}!"
    }


@router.post("/echo")
def echo_message(payload: MessageRequest):
    return {
        "you_sent": payload.message
    }


@router.post("/greet", response_model=GreetResponse)
def greet_user(payload: GreetRequest):
    return {
        "reply": f"Halo {payload.name}, kamu bilang: {payload.message}"
    }


@router.get("/search")
def search(q: str | None = None, limit: int = 10):
    return {
        "query": q,
        "limit": limit,
        "results": []
    }
