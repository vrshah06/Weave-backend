from typing import Optional

from bson import ObjectId

from core.database import get_db
from utils.clock import utc_now


def new_import_id() -> ObjectId:
    return ObjectId()


async def save(import_id: ObjectId, document: dict) -> dict:
    document = {"_id": import_id, **document, "created_at": utc_now()}
    await get_db().imports.insert_one(document)
    return document


async def find_by_id(import_id: ObjectId) -> Optional[dict]:
    return await get_db().imports.find_one({"_id": import_id})


async def list_page(limit: int, offset: int) -> tuple[list[dict], int]:
    total = await get_db().imports.count_documents({})
    cursor = get_db().imports.find({}, {"rows": 0, "cancelled": 0}).sort("created_at", -1).skip(offset).limit(limit)
    return await cursor.to_list(length=limit), total
