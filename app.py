from src.config import Config
from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

def get_allowed_origins():
    origins_str = Config.ALLOWED_ORIGINS
    origins = [origin.strip() for origin in origins_str.split(",")]
    origins = [origin for origin in origins if origin]
    return origins

allowed_origins = get_allowed_origins()

app = FastAPI(title=f"{Config.APP_NAME} API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="X-API-KEY header is missing")
    if x_api_key != Config.HTTP_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

class ApiRequest(BaseModel):
    org_id: int

@app.get("/status")
async def status():
    return JSONResponse(content={"status": "running"}, status_code=200)

@app.post("/test")
async def test_fn(request: ApiRequest, api_key: str = Depends(verify_api_key)):
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