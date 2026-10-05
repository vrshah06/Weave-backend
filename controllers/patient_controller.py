from typing import Optional

from controllers.presenters import present_appointment, present_patient
from models.appointment_models import AppointmentResponse
from models.common import Page
from models.patient_models import PatientResponse
from services import patient_service


async def list_patients(search: Optional[str], limit: int, offset: int) -> Page[PatientResponse]:
    patients, total = await patient_service.list_page(search, limit, offset)
    return Page(items=[present_patient(p) for p in patients], total=total, limit=limit, offset=offset)


async def get_patient(patient_id: str) -> PatientResponse:
    return present_patient(await patient_service.get(patient_id))


async def list_patient_appointments(patient_id: str) -> list[AppointmentResponse]:
    return [present_appointment(a) for a in await patient_service.list_appointments(patient_id)]
