from fastapi import FastAPI, Request
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.api.v1 import auth, system, conversations
from app.core.config import settings
from app.core.rate_limit import limiter

app = FastAPI(title=settings.app_name)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/")
def root():
    return {"message": "Welcome to VeloraAi API", "version": "0.1.1"}


@app.middleware("http")
async def rate_limit_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.include_router(conversations.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
