from typing import Optional

from fastapi import APIRouter, Query

from controllers import patient_controller
from models.appointment_models import AppointmentResponse
from models.common import Page
from models.patient_models import PatientResponse

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=Page[PatientResponse])
async def list_patients(search: Optional[str] = Query(None, max_length=100), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return await patient_controller.list_patients(search, limit, offset)


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: str):
    return await patient_controller.get_patient(patient_id)


@router.get("/{patient_id}/appointments", response_model=list[AppointmentResponse])
async def list_patient_appointments(patient_id: str):
    return await patient_controller.list_patient_appointments(patient_id)
