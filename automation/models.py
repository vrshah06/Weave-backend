from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ProcessStatus(str, Enum):
    SENT = "SENT"
    READY_TO_SEND = "READY_TO_SEND"
    SKIP_ALREADY_SENT = "SKIP_ALREADY_SENT"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    WEAVE_NOT_LOADED = "WEAVE_NOT_LOADED"
    MESSAGES_NOT_FOUND = "MESSAGES_NOT_FOUND"
    NEW_MESSAGE_NOT_FOUND = "NEW_MESSAGE_NOT_FOUND"
    TO_FIELD_NOT_FOUND = "TO_FIELD_NOT_FOUND"
    SEARCH_TIMEOUT = "SEARCH_TIMEOUT"
    NO_RECIPIENT_FOUND = "NO_RECIPIENT_FOUND"
    AMBIGUOUS_RECIPIENT = "AMBIGUOUS_RECIPIENT"
    RECIPIENT_MISMATCH = "RECIPIENT_MISMATCH"
    CONVERSATION_LOAD_TIMEOUT = "CONVERSATION_LOAD_TIMEOUT"
    MESSAGE_INPUT_NOT_FOUND = "MESSAGE_INPUT_NOT_FOUND"
    SEND_BUTTON_NOT_FOUND = "SEND_BUTTON_NOT_FOUND"
    SEND_UNCONFIRMED = "SEND_UNCONFIRMED"
    NETWORK_ERROR = "NETWORK_ERROR"
    BROWSER_ERROR = "BROWSER_ERROR"
    INVALID_PHONE = "INVALID_PHONE"
    INVALID_CSV = "INVALID_CSV"
    NOT_DELIVERED = "NOT_DELIVERED"
    FAILED = "FAILED"


@dataclass
class Appointment:
    row_index: int
    patient_name: str
    phone: str
    appointment_date: str
    appointment_time: str
    normalized_phone: str
    dedup_key: str


@dataclass
class RecipientSearchResult:
    raw_text: str
    name: Optional[str] = None
    phone: Optional[str] = None
    role_label: Optional[str] = None


@dataclass
class ProcessResult:
    appointment: Appointment
    status: ProcessStatus
    error: Optional[str] = None
    message_hash: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
