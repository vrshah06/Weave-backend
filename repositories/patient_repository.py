import re

from core.database import get_db


async def find_by_id(patient_id):
    return await get_db().patients.find_one({"_id": patient_id})


async def find_by_name_and_phone(full_name: str, phone: str):
    return await get_db().patients.find_one({
        "phone": phone,
        "fullName": {"$regex": f"^\\s*{re.escape(full_name.strip())}\\s*$", "$options": "i"}
    })


async def create(patient: dict):
    res = await get_db().patients.insert_one(patient)
    return await find_by_id(res.inserted_id)


async def list_all():
    return await get_db().patients.find().sort([("lastName", 1), ("firstName", 1)]).to_list(length=1000)
