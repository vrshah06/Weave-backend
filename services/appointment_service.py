from datetime import date
from typing import Optional

from core.errors import NotFoundError
from models.enums import REQUEUEABLE_APPOINTMENT_STATUSES, AppointmentStatus
from repositories import appointment_repository
from utils.clock import utc_now
from utils.object_ids import parse_body_ids, parse_path_id


async def list_for_date(appointment_date: date, status: Optional[AppointmentStatus]) -> list[dict]:
    return await appointment_repository.list_by_date_with_patient(appointment_date, status)


async def list_dates() -> list[str]:
    return await appointment_repository.list_dates()


async def get(appointment_id: str) -> dict:
    appointment = await appointment_repository.find_by_id_with_patient(parse_path_id(appointment_id, "Appointment"))
    if not appointment:
        raise NotFoundError("Appointment not found")
    return appointment


async def set_excluded(appointment_ids: list[str], excluded: bool) -> tuple[int, int]:
    return await appointment_repository.set_excluded(parse_body_ids(appointment_ids, "appointmentIds"), excluded)


async def requeue(appointment_ids: list[str]) -> tuple[int, int]:
    return await appointment_repository.transition_many(
        parse_body_ids(appointment_ids, "appointmentIds"),
        REQUEUEABLE_APPOINTMENT_STATUSES,
        {"status": AppointmentStatus.PENDING.value, "status_reason": "Re-queued manually"},
    )


async def mark_sent(appointment_ids: list[str]) -> tuple[int, int]:
    return await appointment_repository.transition_many(
        parse_body_ids(appointment_ids, "appointmentIds"),
        (AppointmentStatus.NEEDS_REVIEW,),
        {"status": AppointmentStatus.SENT.value, "status_reason": "Marked as sent after manual review", "sent_at": utc_now()},
    )
