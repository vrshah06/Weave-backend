from core.database import get_db

SETTINGS_ID = "default"


async def find():
    return await get_db().settings.find_one({"_id": SETTINGS_ID})


async def create(settings: dict):
    return await get_db().settings.insert_one({"_id": SETTINGS_ID, **settings})


async def upsert(fields: dict):
    return await get_db().settings.update_one({"_id": SETTINGS_ID}, {"$set": fields}, upsert=True)
