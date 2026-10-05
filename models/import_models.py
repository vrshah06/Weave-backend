from datetime import date, datetime
from typing import Optional

from models.common import ApiModel
from models.enums import ImportRowStatus


class ImportRowResult(ApiModel):
    row: int
    status: ImportRowStatus
    message: Optional[str] = None
    appointment_id: Optional[str] = None
    patient_name: Optional[str] = None
    phone: Optional[str] = None
    appointment_date: Optional[date] = None
    appointment_time: Optional[str] = None


class CancelledAppointment(ApiModel):
    appointment_id: str
    patient_name: str
    appointment_date: date
    appointment_time: str


class ImportCounts(ApiModel):
    rows: int
    created: int
    updated: int
    reactivated: int
    unchanged: int
    cancelled: int
    invalid: int


class ImportResponse(ApiModel):
    id: str
    file_name: str
    dates: list[date]
    counts: ImportCounts
    rows: list[ImportRowResult]
    cancelled: list[CancelledAppointment]
    created_at: datetime


class ImportSummaryResponse(ApiModel):
    id: str
    file_name: str
    dates: list[date]
    counts: ImportCounts
    created_at: datetime
