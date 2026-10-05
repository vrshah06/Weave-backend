from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol


class DriverError(Exception):
    """The browser or Weave is unusable (cannot start, cannot log in, page crashed)."""


class PrepareFailure(str, Enum):
    RECIPIENT_NOT_VERIFIED = "RECIPIENT_NOT_VERIFIED"
    UI_ERROR = "UI_ERROR"


@dataclass(frozen=True)
class Recipient:
    full_name: str
    first_name: str
    last_name: str
    phone: str


@dataclass(frozen=True)
class PrepareResult:
    ok: bool
    failure: Optional[PrepareFailure] = None
    reason: Optional[str] = None

    @classmethod
    def ready(cls) -> "PrepareResult":
        return cls(ok=True)

    @classmethod
    def not_verified(cls, reason: str) -> "PrepareResult":
        return cls(ok=False, failure=PrepareFailure.RECIPIENT_NOT_VERIFIED, reason=reason)

    @classmethod
    def ui_error(cls, reason: str) -> "PrepareResult":
        return cls(ok=False, failure=PrepareFailure.UI_ERROR, reason=reason)


class SendStatus(str, Enum):
    SENT = "SENT"
    NOT_DELIVERED = "NOT_DELIVERED"
    UNCONFIRMED = "UNCONFIRMED"


@dataclass(frozen=True)
class SendResult:
    status: SendStatus
    reason: Optional[str] = None


class MessagingDriver(Protocol):
    async def start(self) -> None: ...

    async def authenticate(self) -> None: ...

    async def prepare_message(self, recipient: Recipient, text: str) -> PrepareResult:
        """Open a verified conversation with the recipient and type the text, without sending."""
        ...

    async def discard_draft(self) -> None: ...

    async def send_prepared_message(self, text: str) -> SendResult: ...

    async def capture_screenshot(self) -> Optional[bytes]: ...

    async def reset(self) -> None:
        """Return the browser to a known page after an error."""
        ...

    async def close(self) -> None: ...
