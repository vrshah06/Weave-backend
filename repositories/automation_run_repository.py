from bson import ObjectId

from core.database import get_db


async def create(run: dict):
    res = await get_db().automation_runs.insert_one(run)
    return res.inserted_id


async def find_by_id(run_id: str):
    return await get_db().automation_runs.find_one({"_id": ObjectId(run_id)})


async def find_latest():
    return await get_db().automation_runs.find_one({}, sort=[("startedAt", -1)])


async def list_all():
    return await get_db().automation_runs.find().sort("startedAt", -1).to_list(length=100)


async def update(run_id, fields: dict):
    return await get_db().automation_runs.update_one({"_id": ObjectId(run_id)}, {"$set": fields})
