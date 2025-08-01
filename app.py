from boot import app_boot
from src.config import Config
from src.utils import now
from fastapi import FastAPI, Header, HTTPException, Depends, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from src.utils.performance import performance_tracker
import logging
from typing import AsyncGenerator
from src.models.api_request import ApiRequest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events.
    """
    # Startup
    await app_boot()
    logger = logging.getLogger(__name__)
    logger.info(f"Starting API in {Config.APP_MODE} mode")
    
    yield  # App is running
    
    # Shutdown
    # await processor.cleanup()
    logger.info("Shutting down API")

    
def get_allowed_origins():
    origins_str = Config.ALLOWED_ORIGINS
    if not origins_str:  # Handle empty/None case
        return ["http://localhost:3000"] if Config.APP_MODE != "production" else []
    
    origins = [origin.strip() for origin in origins_str.split(",")]
    return [origin for origin in origins if origin]


allowed_origins = get_allowed_origins()
if Config.APP_MODE == "production" and not allowed_origins:
    raise ValueError("ALLOWED_ORIGINS must be set in production")

app = FastAPI(title=f"{Config.APP_NAME} API", lifespan=lifespan)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify_api_key(x_api_key: str | None=Header(None)):
    if Config.HTTP_SECRET is None:
        raise HTTPException(status_code=500, detail="API key not configured")
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="X-API-KEY header is missing")
    
    # Use secure comparison to prevent timing attacks
    import secrets
    if not secrets.compare_digest(x_api_key, Config.HTTP_SECRET):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

    
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/health")
@limiter.limit("2/minute")
async def health(request: Request, response: Response):
    return JSONResponse(content={
        "status": "healthy",
        "mode": Config.APP_MODE,
        "timestamp": now().isoformat(),
        "boot_time": performance_tracker.get_boot_time()
    }, status_code=200)


@app.post("/test")
@limiter.limit("5/minute")
async def test_fn(request: ApiRequest, response: Response, api_key: str=Depends(verify_api_key)):
    try:
        # Simulate some processing logic
        
        response = {
            "success": True,
            "result": {
                "message": "Test function executed successfully",
                "org_id": request.org_id
            }
        }
        
        if not response["success"]:
            return JSONResponse(content={"error": response["error"]}, status_code=400)
        
        return JSONResponse(content=response["result"], status_code=200)
        
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)
