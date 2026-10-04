import os
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from automation.logging_utils import setup_logger
from core.config import CORS_ORIGINS
from core.database import close_db, get_db
from core.exceptions import (
    AutomationAlreadyRunningError,
    InvalidRequestError,
    NoActiveRunError,
    NoAppointmentsSelectedError,
    NotFoundError,
)
from routes import api_router

logger = setup_logger("weave_api")

ERROR_STATUS_CODES = {
    AutomationAlreadyRunningError: 400,
    NoAppointmentsSelectedError: 400,
    NoActiveRunError: 400,
    NotFoundError: 404,
    InvalidRequestError: 400,
}

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
    allow_credentials=CORS_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def handle_domain_error(request: Request, exc: Exception):
    return JSONResponse(status_code=ERROR_STATUS_CODES[type(exc)], content={"detail": str(exc)})


for error_type in ERROR_STATUS_CODES:
    app.add_exception_handler(error_type, handle_domain_error)

app.include_router(api_router, prefix="/api")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    reload = os.environ.get("RELOAD", "false").lower() in ("true", "1", "yes")
    logger.info(f"Weave Automation API starting on {host}:{port}")
    uvicorn.run("app:app", host=host, port=port, reload=reload)
