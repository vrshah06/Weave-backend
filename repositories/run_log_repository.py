from typing import Optional

from bson import ObjectId

from core.database import get_db
from models.enums import LogLevel
from utils.clock import utc_now


async def append(run_id: ObjectId, level: LogLevel, event: str, message: str, appointment_id: Optional[ObjectId] = None) -> None:
    await get_db().run_logs.insert_one({
        "run_id": run_id,
        "appointment_id": appointment_id,
        "level": level.value,
        "event": event,
        "message": message,
        "created_at": utc_now(),
    })


async def list_after(run_id: ObjectId, after_id: Optional[ObjectId], limit: int) -> list[dict]:
    query: dict = {"run_id": run_id}
    if after_id:
        query["_id"] = {"$gt": after_id}
    return await get_db().run_logs.find(query).sort("_id", 1).limit(limit).to_list(length=limit)
