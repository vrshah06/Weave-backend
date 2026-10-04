from typing import Optional

from fastapi import APIRouter

from controllers import appointment_controller

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("")
async def get_appointments(date: Optional[str] = None):
    return await appointment_controller.get_appointments(date)


@router.post("/selection")
async def update_selection(payload: dict):
    return await appointment_controller.update_selection(payload)

@router.get("/dates")
async def get_available_dates():
    return await appointment_controller.get_available_dates()
