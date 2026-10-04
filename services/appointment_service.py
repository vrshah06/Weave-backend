from datetime import datetime
from typing import Optional

from bson import ObjectId

from repositories import appointment_repository, patient_repository
from utils.formatters import mask_phone, parse_time_to_minutes


async def get_appointments_for_date(date: Optional[str]) -> dict:
    target_date = date
    if not target_date:
        latest = await appointment_repository.find_latest()
        target_date = latest["appointmentDate"] if latest else datetime.now().strftime("%Y-%m-%d")

    appts = await appointment_repository.list_by_date(target_date)

    formatted = []
    for a in appts:
        patient = await patient_repository.find_by_id(a.get("patientId"))
        formatted.append({
            "id": str(a["_id"]),
            "patientName": patient["fullName"] if patient else "Unknown",
            "phone": patient["phone"] if patient else "",
            "maskedPhone": mask_phone(patient["phone"] if patient else ""),
            "appointmentDate": a["appointmentDate"],
            "appointmentTime": a["appointmentTime"],
            "provider": a.get("provider", "General Practice"),
            "reminderSelected": a.get("reminderSelected", True),
            "reminderStatus": a.get("reminderStatus", "PENDING")
        })

    formatted.sort(key=lambda x: parse_time_to_minutes(x["appointmentTime"]))
    return {"date": target_date, "appointments": formatted}


async def set_reminder_selection(appointment_ids: list, selected: bool) -> None:
    ids = [ObjectId(aid) for aid in appointment_ids]
    await appointment_repository.update_many(ids, {"reminderSelected": bool(selected), "updatedAt": datetime.utcnow()})


async def get_available_dates() -> list:
    dates = await appointment_repository.distinct_dates()
    dates.sort(reverse=True)
    return dates
