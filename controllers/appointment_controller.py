from datetime import date
from typing import Optional

from controllers.presenters import present_appointment
from models.appointment_models import (
    AppointmentBulkUpdateResponse,
    AppointmentDatesResponse,
    AppointmentListResponse,
    AppointmentResponse,
)
from models.enums import AppointmentStatus
from services import appointment_service


async def list_appointments(appointment_date: date, status: Optional[AppointmentStatus]) -> AppointmentListResponse:
    appointments = await appointment_service.list_for_date(appointment_date, status)
    return AppointmentListResponse(appointment_date=appointment_date, appointments=[present_appointment(a) for a in appointments])


async def list_dates() -> AppointmentDatesResponse:
    return AppointmentDatesResponse(dates=[date.fromisoformat(d) for d in await appointment_service.list_dates()])


async def get_appointment(appointment_id: str) -> AppointmentResponse:
    return present_appointment(await appointment_service.get(appointment_id))


async def set_excluded(appointment_ids: list[str], excluded: bool) -> AppointmentBulkUpdateResponse:
    matched, updated = await appointment_service.set_excluded(appointment_ids, excluded)
    return AppointmentBulkUpdateResponse(matched=matched, updated=updated)


async def requeue(appointment_ids: list[str]) -> AppointmentBulkUpdateResponse:
    matched, updated = await appointment_service.requeue(appointment_ids)
    return AppointmentBulkUpdateResponse(matched=matched, updated=updated)


async def mark_sent(appointment_ids: list[str]) -> AppointmentBulkUpdateResponse:
    matched, updated = await appointment_service.mark_sent(appointment_ids)
    return AppointmentBulkUpdateResponse(matched=matched, updated=updated)
