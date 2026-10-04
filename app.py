import os
import sys
from contextlib import asynccontextmanager

import socketio
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv()

from database import get_db, close_db
from routers import router
from config import CORS_ORIGINS
from socket_manager import sio
from src.logging_utils import setup_logger

logger = setup_logger("weave_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_db()
    logger.info("MongoDB connection initialized")
    yield
    close_db()
    logger.info("MongoDB connection closed")


app = FastAPI(title="Weave Automation API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    # Browsers reject credentialed requests to a wildcard origin
    allow_credentials=CORS_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# Wrap FastAPI with Socket.IO ASGI app. Serve `app:sio_app`, not `app:app`,
# otherwise Socket.IO connections are not handled.
sio_app = socketio.ASGIApp(socketio_server=sio, other_asgi_app=app)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    reload = os.environ.get("RELOAD", "false").lower() in ("true", "1", "yes")
    logger.info(f"Weave Automation API starting on {host}:{port}")
    uvicorn.run("app:sio_app", host=host, port=port, reload=reload)
