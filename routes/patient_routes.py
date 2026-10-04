from fastapi import APIRouter

from controllers import patient_controller

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("")
async def list_patients():
    return await patient_controller.list_patients()


@router.get("/{patient_id}/history")
async def get_history(patient_id: str):
    return await patient_controller.get_history(patient_id)
