import re
from datetime import datetime
from typing import Optional

from core.exceptions import InvalidRequestError
from services import appointment_service

ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


def _validate_iso_date(value: str) -> str:
    try:
        if not ISO_DATE_PATTERN.fullmatch(value):
            raise ValueError
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise InvalidRequestError(f"Invalid date '{value}'. Use YYYY-MM-DD, e.g. 2026-10-02.")
    return value


async def get_appointments(date: Optional[str]) -> dict:
    if date is not None:
        date = _validate_iso_date(date)
    return await appointment_service.get_appointments_for_date(date)


async def update_selection(payload: dict) -> dict:
    appointment_ids = payload.get("appointmentIds", [])
    selected = payload.get("selected", False)
    await appointment_service.set_reminder_selection(appointment_ids, selected)
    return {"message": "Appointment selection updated", "count": len(appointment_ids), "selected": selected}


async def get_available_dates() -> dict:
    return {"dates": await appointment_service.get_available_dates()}
