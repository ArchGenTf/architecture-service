import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv
import os

load_dotenv()

from routes import api

import logging
from contextlib import asynccontextmanager
from utils.provider_manager import ProviderManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = ProviderManager()
    app.state.provider_manager = manager
    
    # Startup validation
    status = await manager.health_check()
    logger.info(f"MongoDB: {status.get('mongodb', 'Unknown').capitalize()}")
    
    provider = status.get('provider', 'Mock')
    if provider == "OpenAI":
        logger.info("OpenAI: Available\nDeepSeek: Unavailable\nOllama: Unavailable")
    elif provider == "DeepSeek":
        logger.info("OpenAI: Unavailable\nDeepSeek: Available\nOllama: Unavailable")
    elif provider == "Ollama":
        logger.info("OpenAI: Unavailable\nDeepSeek: Unavailable\nOllama: Available")
    else:
        logger.info("OpenAI: Unavailable\nDeepSeek: Unavailable\nOllama: Unavailable")
        
    logger.info(f"Selected Provider: {provider}")
    yield

app = FastAPI(lifespan=lifespan)

from fastapi.middleware.cors import CORSMiddleware
import os

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router)

@app.get("/healthz")
async def healthz():
    manager = app.state.provider_manager
    return await manager.health_check()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
