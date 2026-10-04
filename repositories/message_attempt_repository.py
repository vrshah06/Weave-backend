from datetime import datetime

from bson import ObjectId

from core.database import get_db


async def create(attempt: dict):
    return await get_db().message_attempts.insert_one(attempt)


async def count_by_appointment(appointment_id):
    return await get_db().message_attempts.count_documents({"appointmentId": appointment_id})


async def list_by_run(run_id: str):
    return await get_db().message_attempts.find({"automationRunId": ObjectId(run_id)}).to_list(length=1000)


async def list_by_patient(patient_id: str):
    return await get_db().message_attempts.find({"patientId": ObjectId(patient_id)}).sort("createdAt", -1).to_list(length=100)


async def mark_confirmed(attempt_id):
    return await get_db().message_attempts.update_one(
        {"_id": attempt_id},
        {"$set": {"status": "CONFIRMED", "confirmedAt": datetime.utcnow()}}
    )
