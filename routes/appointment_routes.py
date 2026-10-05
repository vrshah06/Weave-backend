from typing import Optional

from fastapi import APIRouter, Query

from controllers import appointment_controller
from models.appointment_models import (
    AppointmentBulkUpdateResponse,
    AppointmentDatesResponse,
    AppointmentExclusionRequest,
    AppointmentIdsRequest,
    AppointmentListResponse,
    AppointmentResponse,
)
from models.common import IsoDate
from models.enums import AppointmentStatus

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("", response_model=AppointmentListResponse, summary="Appointments on a date, ordered by time")
async def list_appointments(appointment_date: IsoDate = Query(alias="date"), status: Optional[AppointmentStatus] = None):
    return await appointment_controller.list_appointments(appointment_date, status)


@router.get("/dates", response_model=AppointmentDatesResponse, summary="Dates that have appointments, newest first")
async def list_dates():
    return await appointment_controller.list_dates()


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(appointment_id: str):
    return await appointment_controller.get_appointment(appointment_id)


@router.post("/exclusions", response_model=AppointmentBulkUpdateResponse, summary="Exclude or include appointments in future runs")
async def set_excluded(request: AppointmentExclusionRequest):
    return await appointment_controller.set_excluded(request.appointment_ids, request.excluded)


@router.post("/requeue", response_model=AppointmentBulkUpdateResponse, summary="Move FAILED, SKIPPED or NEEDS_REVIEW appointments back to PENDING")
async def requeue(request: AppointmentIdsRequest):
    return await appointment_controller.requeue(request.appointment_ids)


@router.post("/mark-sent", response_model=AppointmentBulkUpdateResponse, summary="Confirm NEEDS_REVIEW appointments were actually sent")
async def mark_sent(request: AppointmentIdsRequest):
    return await appointment_controller.mark_sent(request.appointment_ids)
