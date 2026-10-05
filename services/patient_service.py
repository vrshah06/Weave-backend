from typing import Optional

from core.errors import NotFoundError
from repositories import appointment_repository, patient_repository
from utils.object_ids import parse_path_id


async def list_page(search: Optional[str], limit: int, offset: int) -> tuple[list[dict], int]:
    return await patient_repository.list_page(search, limit, offset)


async def get(patient_id: str) -> dict:
    patient = await patient_repository.find_by_id(parse_path_id(patient_id, "Patient"))
    if not patient:
        raise NotFoundError("Patient not found")
    return patient


async def list_appointments(patient_id: str) -> list[dict]:
    patient = await get(patient_id)
    return await appointment_repository.list_for_patient(patient["_id"])
