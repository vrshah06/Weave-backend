from enum import Enum


class AppointmentStatus(str, Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CANCELLED = "CANCELLED"


REQUEUEABLE_APPOINTMENT_STATUSES = (AppointmentStatus.FAILED, AppointmentStatus.SKIPPED, AppointmentStatus.NEEDS_REVIEW)
CANCELLABLE_APPOINTMENT_STATUSES = (AppointmentStatus.PENDING, AppointmentStatus.FAILED, AppointmentStatus.SKIPPED)


class RunMode(str, Enum):
    DRY_RUN = "DRY_RUN"
    SEND = "SEND"


class RunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


ACTIVE_RUN_STATUSES = (RunStatus.QUEUED, RunStatus.RUNNING)


class RunItemStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    DRY_RUN_VERIFIED = "DRY_RUN_VERIFIED"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class LogLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ImportRowStatus(str, Enum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    REACTIVATED = "REACTIVATED"
    UNCHANGED = "UNCHANGED"
    DUPLICATE_IN_FILE = "DUPLICATE_IN_FILE"
    INVALID = "INVALID"
