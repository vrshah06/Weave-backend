import re
from typing import Optional, cast

from bson import ObjectId
from pymongo import ReturnDocument

from core.database import get_db
from utils.clock import utc_now
from utils.names import PatientName


async def upsert(patient: PatientName, phone: str, phone_raw: str) -> dict:
    now = utc_now()
    # Upsert with ReturnDocument.AFTER always returns the document.
    return cast(dict, await get_db().patients.find_one_and_update(
        {"name_key": patient.name_key, "phone": phone},
        {
            "$setOnInsert": {"created_at": now},
            "$set": {
                "full_name": patient.full_name,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "phone_raw": phone_raw,
                "updated_at": now,
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    ))


async def find_by_id(patient_id: ObjectId) -> Optional[dict]:
    return await get_db().patients.find_one({"_id": patient_id})


async def list_page(search: Optional[str], limit: int, offset: int) -> tuple[list[dict], int]:
    query: dict = {}
    if search and search.strip():
        conditions = [{"name_key": {"$regex": re.escape(search.strip().lower())}}]
        digits = re.sub(r"\D", "", search)
        if digits:
            conditions.append({"phone": {"$regex": re.escape(digits)}})
        query = {"$or": conditions}
    total = await get_db().patients.count_documents(query)
    cursor = get_db().patients.find(query).sort([("last_name", 1), ("first_name", 1)]).skip(offset).limit(limit)
    return await cursor.to_list(length=limit), total
