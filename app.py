import logging
import os
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core import database
from core.config import config
from core.errors import register_error_handlers
from core.logging import configure_logging
from routes import api_router
from automation.weave_driver import WeaveDriver
from worker.worker import Worker

configure_logging(config.log_level)
logger = logging.getLogger("weave.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not config.api_key:
        raise RuntimeError("API_KEY is not set; refusing to start an unauthenticated API")
    database.connect()
    await database.ensure_indexes()
    
    worker = Worker(driver_factory=WeaveDriver)
    # The worker connects to the DB internally as well, which is safe.
    worker_task = asyncio.create_task(worker.run_forever())
    
    logger.info("API started (environment=%s)", config.environment)
    yield
    
    worker.shutdown.set()
    try:
        await asyncio.wait_for(worker_task, timeout=10.0)
    except asyncio.TimeoutError:
        pass
        
    await database.close()


app = FastAPI(title="Weave Reminder API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    # Browsers reject credentialed requests to a wildcard origin
    allow_credentials=config.cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)
app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run("app:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
