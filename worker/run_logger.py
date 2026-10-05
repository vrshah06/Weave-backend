import logging
from typing import Optional

from bson import ObjectId

from models.enums import LogLevel
from repositories import run_log_repository

logger = logging.getLogger("weave.worker")

PYTHON_LEVELS = {LogLevel.INFO: logging.INFO, LogLevel.WARNING: logging.WARNING, LogLevel.ERROR: logging.ERROR}


class RunLogger:
    def __init__(self, run_id: ObjectId):
        self.run_id = run_id

    async def log(self, level: LogLevel, event: str, message: str, appointment_id: Optional[ObjectId] = None) -> None:
        logger.log(PYTHON_LEVELS[level], "[run %s] %s: %s", self.run_id, event, message)
        try:
            await run_log_repository.append(self.run_id, level, event, message, appointment_id)
        except Exception:
            logger.exception("Could not persist run log for run %s", self.run_id)

    async def info(self, event: str, message: str, appointment_id: Optional[ObjectId] = None) -> None:
        await self.log(LogLevel.INFO, event, message, appointment_id)

    async def warning(self, event: str, message: str, appointment_id: Optional[ObjectId] = None) -> None:
        await self.log(LogLevel.WARNING, event, message, appointment_id)

    async def error(self, event: str, message: str, appointment_id: Optional[ObjectId] = None) -> None:
        await self.log(LogLevel.ERROR, event, message, appointment_id)
