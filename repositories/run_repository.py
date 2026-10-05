from datetime import date, timedelta
from typing import Optional

from bson import ObjectId
from pymongo import ReturnDocument

from core.database import get_db
from models.enums import ACTIVE_RUN_STATUSES, RunMode, RunStatus
from utils.clock import utc_now

COUNT_FIELDS = ("total", "processed", "sent", "dry_run_verified", "failed", "skipped", "needs_review")


async def create(appointment_date: date, mode: RunMode) -> dict:
    document = {
        "appointment_date": appointment_date.isoformat(),
        "mode": mode.value,
        "status": RunStatus.QUEUED.value,
        "stop_requested": False,
        "counts": {name: 0 for name in COUNT_FIELDS},
        "error": None,
        "worker_id": None,
        "queued_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "heartbeat_at": None,
    }
    result = await get_db().runs.insert_one(document)
    document["_id"] = result.inserted_id
    return document


async def find_by_id(run_id: ObjectId) -> Optional[dict]:
    return await get_db().runs.find_one({"_id": run_id})


async def find_latest() -> Optional[dict]:
    return await get_db().runs.find_one({}, sort=[("queued_at", -1)])


async def find_active_for_date(appointment_date: date) -> Optional[dict]:
    return await get_db().runs.find_one({
        "appointment_date": appointment_date.isoformat(),
        "status": {"$in": [s.value for s in ACTIVE_RUN_STATUSES]},
    })


async def list_page(status: Optional[RunStatus], limit: int, offset: int) -> tuple[list[dict], int]:
    query = {"status": status.value} if status else {}
    total = await get_db().runs.count_documents(query)
    cursor = get_db().runs.find(query).sort("queued_at", -1).skip(offset).limit(limit)
    return await cursor.to_list(length=limit), total


async def claim_next_queued(worker_id: str) -> Optional[dict]:
    now = utc_now()
    return await get_db().runs.find_one_and_update(
        {"status": RunStatus.QUEUED.value},
        {"$set": {"status": RunStatus.RUNNING.value, "worker_id": worker_id, "started_at": now, "heartbeat_at": now}},
        sort=[("queued_at", 1)],
        return_document=ReturnDocument.AFTER,
    )


async def set_total(run_id: ObjectId, total: int) -> None:
    await get_db().runs.update_one({"_id": run_id}, {"$set": {"counts.total": total}})


async def record_outcome(run_id: ObjectId, count_field: str) -> None:
    await get_db().runs.update_one({"_id": run_id}, {"$inc": {"counts.processed": 1, f"counts.{count_field}": 1}})


async def heartbeat(run_id: ObjectId) -> None:
    await get_db().runs.update_one({"_id": run_id}, {"$set": {"heartbeat_at": utc_now()}})


async def is_stop_requested(run_id: ObjectId) -> bool:
    run = await get_db().runs.find_one({"_id": run_id}, {"stop_requested": 1})
    return bool(run and run.get("stop_requested"))


async def cancel_if_queued(run_id: ObjectId) -> Optional[dict]:
    return await get_db().runs.find_one_and_update(
        {"_id": run_id, "status": RunStatus.QUEUED.value},
        {"$set": {"status": RunStatus.CANCELLED.value, "finished_at": utc_now()}},
        return_document=ReturnDocument.AFTER,
    )


async def request_stop_if_running(run_id: ObjectId) -> Optional[dict]:
    return await get_db().runs.find_one_and_update(
        {"_id": run_id, "status": RunStatus.RUNNING.value},
        {"$set": {"stop_requested": True}},
        return_document=ReturnDocument.AFTER,
    )


async def finish(run_id: ObjectId, status: RunStatus, error: Optional[str] = None) -> None:
    await get_db().runs.update_one(
        {"_id": run_id},
        {"$set": {"status": status.value, "error": error, "finished_at": utc_now()}},
    )


async def interrupt_running(reason: str) -> list[ObjectId]:
    running = await get_db().runs.find({"status": RunStatus.RUNNING.value}, {"_id": 1}).to_list(length=None)
    ids = [r["_id"] for r in running]
    if ids:
        await get_db().runs.update_many(
            {"_id": {"$in": ids}},
            {"$set": {"status": RunStatus.INTERRUPTED.value, "error": reason, "finished_at": utc_now()}},
        )
    return ids


def is_heartbeat_stale(run: dict, max_age_seconds: int) -> bool:
    heartbeat_at = run.get("heartbeat_at")
    return heartbeat_at is None or utc_now() - heartbeat_at > timedelta(seconds=max_age_seconds)
