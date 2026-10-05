from datetime import date, datetime
from typing import Optional

from models.common import ApiModel, IsoDate
from models.enums import LogLevel, RunItemStatus, RunMode, RunStatus


class RunCreateRequest(ApiModel):
    appointment_date: IsoDate
    mode: RunMode


class RunCounts(ApiModel):
    total: int
    processed: int
    remaining: int
    sent: int
    dry_run_verified: int
    failed: int
    skipped: int
    needs_review: int


class RunResponse(ApiModel):
    id: str
    appointment_date: date
    mode: RunMode
    status: RunStatus
    stop_requested: bool
    counts: RunCounts
    error: Optional[str] = None
    queued_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    heartbeat_at: Optional[datetime] = None


class RunItemResponse(ApiModel):
    id: str
    run_id: str
    appointment_id: str
    patient_name: str
    appointment_time: str
    status: RunItemStatus
    reason: Optional[str] = None
    screenshot_url: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None


class RunLogResponse(ApiModel):
    id: str
    run_id: str
    appointment_id: Optional[str] = None
    level: LogLevel
    event: str
    message: str
    created_at: datetime
