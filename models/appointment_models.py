from datetime import date, datetime
from typing import Optional

from pydantic import Field

from models.common import ApiModel
from models.enums import AppointmentStatus


class AppointmentResponse(ApiModel):
    id: str
    patient_id: str
    patient_name: str
    phone: str
    appointment_date: date
    appointment_time: str
    provider: str
    status: AppointmentStatus
    status_reason: Optional[str] = None
    excluded: bool
    sent_at: Optional[datetime] = None
    updated_at: datetime


class AppointmentListResponse(ApiModel):
    appointment_date: date
    appointments: list[AppointmentResponse]


class AppointmentDatesResponse(ApiModel):
    dates: list[date]


class AppointmentIdsRequest(ApiModel):
    appointment_ids: list[str] = Field(min_length=1, max_length=1000)


class AppointmentExclusionRequest(AppointmentIdsRequest):
    excluded: bool


class AppointmentBulkUpdateResponse(ApiModel):
    matched: int
    updated: int
