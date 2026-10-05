from typing import Optional, cast

from pymongo import ReturnDocument

from core.database import get_db
from utils.clock import utc_now

SETTINGS_ID = "clinic"


async def find() -> Optional[dict]:
    return await get_db().settings.find_one({"_id": SETTINGS_ID})


async def save(fields: dict) -> dict:
    return cast(dict, await get_db().settings.find_one_and_update(
        {"_id": SETTINGS_ID}, {"$set": {**fields, "updated_at": utc_now()}}, upsert=True, return_document=ReturnDocument.AFTER
    ))
