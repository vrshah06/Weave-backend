from datetime import datetime

from core.database import get_db


async def find_by_id(appointment_id):
    return await get_db().appointments.find_one({"_id": appointment_id})


async def find_one(query: dict):
    return await get_db().appointments.find_one(query)


async def create(appointment: dict):
    return await get_db().appointments.insert_one(appointment)


async def find_latest():
    return await get_db().appointments.find_one({}, sort=[("appointmentDate", -1)])


async def list_by_date(appointment_date: str):
    return await get_db().appointments.find({"appointmentDate": appointment_date}).to_list(length=1000)


async def list_by_query(query: dict):
    return await get_db().appointments.find(query).to_list(length=1000)


async def list_recent(limit: int = 20, sort_by_updated: bool = False):
    cursor = get_db().appointments.find()
    if sort_by_updated:
        cursor = cursor.sort("updatedAt", -1)
    return await cursor.limit(limit).to_list(length=limit)


async def distinct_dates():
    return await get_db().appointments.distinct("appointmentDate")


async def update_many(appointment_ids: list, fields: dict):
    return await get_db().appointments.update_many({"_id": {"$in": appointment_ids}}, {"$set": fields})


async def update_all(fields: dict):
    return await get_db().appointments.update_many({}, {"$set": fields})


async def update_status(appointment_id, status: str):
    return await get_db().appointments.update_one(
        {"_id": appointment_id},
        {"$set": {"reminderStatus": status, "updatedAt": datetime.utcnow()}}
    )
