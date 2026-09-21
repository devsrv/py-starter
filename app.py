import logging
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from boot import app_boot
from src.config import Config
from src.models.api_request import ApiRequest
from src.utils import now
from src.utils.performance import performance_tracker
from src.utils.rate_limiter import limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown hooks."""
    await app_boot()
    logger.info("Starting API in %s mode", Config.APP_MODE)

    yield  # App is running

    # Close shared resources here if you initialised them at startup, e.g.
    # await mongo_manager.close()  # noqa: ERA001
    logger.info("Shutting down API")


app = FastAPI(title=f"{Config.APP_NAME} API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify_api_key(x_api_key: str | None = Header(None)) -> str:
    """Dependency that checks the X-API-KEY header against HTTP_SECRET."""
    if not Config.HTTP_SECRET:
        raise HTTPException(status_code=500, detail="API key not configured")
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="X-API-KEY header is missing")
    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(x_api_key, Config.HTTP_SECRET):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/health")
@limiter.limit("60/minute")
async def health(request: Request, response: Response) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "mode": Config.APP_MODE,
            "timestamp": now().isoformat(),
            "boot_time": performance_tracker.get_boot_time(),
        },
    )


@app.post("/test")
@limiter.limit("5/minute")
async def test_fn(
    request: Request,  # noqa: ARG001 - required by slowapi
    response: Response,  # noqa: ARG001
    payload: ApiRequest,
    _api_key: str = Depends(verify_api_key),
) -> JSONResponse:
    """Sample protected endpoint. Copy this shape for your own routes."""
    result: dict[str, Any] = {
        "message": "Test function executed successfully",
        "org_id": payload.org_id,
    }
    return JSONResponse(status_code=200, content=result)
