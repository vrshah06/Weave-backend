from datetime import date
from typing import Optional

from bson import ObjectId
from pymongo import ReturnDocument

from core.database import get_db
from models.enums import AppointmentStatus
from utils.clock import utc_now

PATIENT_LOOKUP = [
    {"$lookup": {"from": "patients", "localField": "patient_id", "foreignField": "_id", "as": "patient"}},
    {"$unwind": "$patient"},
]


def _date_key(value: date) -> str:
    return value.isoformat()


async def find_slot(patient_id: ObjectId, appointment_date: date, appointment_time: str) -> Optional[dict]:
    return await get_db().appointments.find_one(
        {"patient_id": patient_id, "appointment_date": _date_key(appointment_date), "appointment_time": appointment_time}
    )


async def create(patient_id: ObjectId, appointment_date: date, appointment_time: str, provider: str, import_id: ObjectId) -> dict:
    now = utc_now()
    document = {
        "patient_id": patient_id,
        "appointment_date": _date_key(appointment_date),
        "appointment_time": appointment_time,
        "provider": provider,
        "status": AppointmentStatus.PENDING.value,
        "status_reason": None,
        "excluded": False,
        "import_id": import_id,
        "sent_at": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await get_db().appointments.insert_one(document)
    document["_id"] = result.inserted_id
    return document


async def update_fields(appointment_id: ObjectId, fields: dict) -> None:
    await get_db().appointments.update_one({"_id": appointment_id}, {"$set": {**fields, "updated_at": utc_now()}})


async def find_by_id(appointment_id: ObjectId) -> Optional[dict]:
    return await get_db().appointments.find_one({"_id": appointment_id})


async def find_by_id_with_patient(appointment_id: ObjectId) -> Optional[dict]:
    results = await (await get_db().appointments.aggregate([{"$match": {"_id": appointment_id}}, *PATIENT_LOOKUP])).to_list(length=1)
    return results[0] if results else None


async def list_by_date_with_patient(appointment_date: date, status: Optional[AppointmentStatus] = None) -> list[dict]:
    match: dict = {"appointment_date": _date_key(appointment_date)}
    if status:
        match["status"] = status.value
    pipeline = [{"$match": match}, *PATIENT_LOOKUP, {"$sort": {"appointment_time": 1, "patient.last_name": 1}}]
    return await (await get_db().appointments.aggregate(pipeline)).to_list(length=None)


async def list_runnable_with_patient(appointment_date: date) -> list[dict]:
    pipeline = [
        {"$match": {"appointment_date": _date_key(appointment_date), "status": AppointmentStatus.PENDING.value, "excluded": False}},
        *PATIENT_LOOKUP,
        {"$sort": {"appointment_time": 1, "patient.last_name": 1}},
    ]
    return await (await get_db().appointments.aggregate(pipeline)).to_list(length=None)


async def count_runnable(appointment_date: date) -> int:
    return await get_db().appointments.count_documents(
        {"appointment_date": _date_key(appointment_date), "status": AppointmentStatus.PENDING.value, "excluded": False}
    )


async def list_dates() -> list[str]:
    dates = await get_db().appointments.distinct("appointment_date")
    return sorted(dates, reverse=True)


async def list_for_patient(patient_id: ObjectId) -> list[dict]:
    pipeline = [{"$match": {"patient_id": patient_id}}, *PATIENT_LOOKUP, {"$sort": {"appointment_date": -1, "appointment_time": -1}}]
    return await (await get_db().appointments.aggregate(pipeline)).to_list(length=None)


async def cancel_missing_from_import(
    appointment_date: date, keep_ids: list[ObjectId], cancellable: tuple[AppointmentStatus, ...], import_id: ObjectId
) -> list[dict]:
    query = {
        "appointment_date": _date_key(appointment_date),
        "_id": {"$nin": keep_ids},
        "status": {"$in": [s.value for s in cancellable]},
    }
    to_cancel = await (await get_db().appointments.aggregate([{"$match": query}, *PATIENT_LOOKUP])).to_list(length=None)
    if to_cancel:
        await get_db().appointments.update_many(
            {"_id": {"$in": [a["_id"] for a in to_cancel]}},
            {"$set": {
                "status": AppointmentStatus.CANCELLED.value,
                "status_reason": "Not present in the latest import for this date",
                "import_id": import_id,
                "updated_at": utc_now(),
            }},
        )
    return to_cancel


async def set_excluded(appointment_ids: list[ObjectId], excluded: bool) -> tuple[int, int]:
    result = await get_db().appointments.update_many(
        {"_id": {"$in": appointment_ids}, "excluded": {"$ne": excluded}},
        {"$set": {"excluded": excluded, "updated_at": utc_now()}},
    )
    matched = await get_db().appointments.count_documents({"_id": {"$in": appointment_ids}})
    return matched, result.modified_count


async def transition_many(appointment_ids: list[ObjectId], from_statuses: tuple[AppointmentStatus, ...], fields: dict) -> tuple[int, int]:
    result = await get_db().appointments.update_many(
        {"_id": {"$in": appointment_ids}, "status": {"$in": [s.value for s in from_statuses]}},
        {"$set": {**fields, "updated_at": utc_now()}},
    )
    matched = await get_db().appointments.count_documents({"_id": {"$in": appointment_ids}})
    return matched, result.modified_count


async def claim_for_sending(appointment_id: ObjectId, run_id: ObjectId) -> bool:
    """Atomically move PENDING -> SENDING; only one sender can ever win."""
    claimed = await get_db().appointments.find_one_and_update(
        {"_id": appointment_id, "status": AppointmentStatus.PENDING.value, "excluded": False},
        {"$set": {"status": AppointmentStatus.SENDING.value, "status_reason": None, "last_run_id": run_id, "updated_at": utc_now()}},
        return_document=ReturnDocument.AFTER,
    )
    return claimed is not None


async def set_status(appointment_id: ObjectId, status: AppointmentStatus, reason: Optional[str], run_id: ObjectId, extra: Optional[dict] = None) -> None:
    await update_fields(appointment_id, {"status": status.value, "status_reason": reason, "last_run_id": run_id, **(extra or {})})


async def release_stuck_sending(reason: str) -> list[ObjectId]:
    stuck = await get_db().appointments.find({"status": AppointmentStatus.SENDING.value}, {"_id": 1}).to_list(length=None)
    ids = [a["_id"] for a in stuck]
    if ids:
        await get_db().appointments.update_many(
            {"_id": {"$in": ids}},
            {"$set": {"status": AppointmentStatus.NEEDS_REVIEW.value, "status_reason": reason, "updated_at": utc_now()}},
        )
    return ids
