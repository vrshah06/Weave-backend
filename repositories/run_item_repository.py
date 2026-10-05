from typing import Optional

from bson import ObjectId

from core.database import get_db
from models.enums import RunItemStatus
from utils.clock import utc_now


async def start(run_id: ObjectId, appointment_id: ObjectId, patient_id: ObjectId) -> ObjectId:
    result = await get_db().run_items.insert_one({
        "run_id": run_id,
        "appointment_id": appointment_id,
        "patient_id": patient_id,
        "status": RunItemStatus.IN_PROGRESS.value,
        "reason": None,
        "screenshot_id": None,
        "started_at": utc_now(),
        "finished_at": None,
    })
    return result.inserted_id


async def finish(item_id: ObjectId, status: RunItemStatus, reason: Optional[str], screenshot_id: Optional[ObjectId]) -> None:
    await get_db().run_items.update_one(
        {"_id": item_id},
        {"$set": {"status": status.value, "reason": reason, "screenshot_id": screenshot_id, "finished_at": utc_now()}},
    )


async def list_for_run_with_details(run_id: ObjectId) -> list[dict]:
    pipeline = [
        {"$match": {"run_id": run_id}},
        {"$lookup": {"from": "appointments", "localField": "appointment_id", "foreignField": "_id", "as": "appointment"}},
        {"$unwind": "$appointment"},
        {"$lookup": {"from": "patients", "localField": "patient_id", "foreignField": "_id", "as": "patient"}},
        {"$unwind": "$patient"},
        {"$sort": {"started_at": 1}},
    ]
    return await (await get_db().run_items.aggregate(pipeline)).to_list(length=None)


async def resolve_in_progress(run_ids: list[ObjectId], needs_review_appointment_ids: list[ObjectId], reason: str) -> None:
    now = utc_now()
    base = {"run_id": {"$in": run_ids}, "status": RunItemStatus.IN_PROGRESS.value}
    await get_db().run_items.update_many(
        {**base, "appointment_id": {"$in": needs_review_appointment_ids}},
        {"$set": {"status": RunItemStatus.NEEDS_REVIEW.value, "reason": reason, "finished_at": now}},
    )
    await get_db().run_items.update_many(
        base, {"$set": {"status": RunItemStatus.FAILED.value, "reason": reason, "finished_at": now}}
    )
