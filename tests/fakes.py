from typing import Awaitable, Callable, Optional

from automation.driver import DriverError, PrepareResult, Recipient, SendResult, SendStatus

FAKE_PNG = b"\x89PNG\r\n\x1a\nfake-screenshot"


class FakeWeaveDriver:
    """Scripted outcomes keyed by E.164 phone: ok, not_verified, ui_error, crash, not_delivered, unconfirmed, send_crash."""

    def __init__(self, outcomes: Optional[dict] = None, *, fail_login: bool = False,
                 before_prepare: Optional[Callable[[Recipient], Awaitable[None]]] = None):
        self.outcomes = outcomes or {}
        self.fail_login = fail_login
        self.before_prepare = before_prepare
        self.prepared: list[tuple[Recipient, str]] = []
        self.sent: list[str] = []
        self.discarded = 0
        self.resets = 0
        self.closed = False
        self.current: Optional[Recipient] = None

    async def start(self) -> None:
        pass

    async def authenticate(self) -> None:
        if self.fail_login:
            raise DriverError("Weave login failed")

    async def prepare_message(self, recipient: Recipient, text: str) -> PrepareResult:
        if self.before_prepare:
            await self.before_prepare(recipient)
        self.prepared.append((recipient, text))
        outcome = self.outcomes.get(recipient.phone, "ok")
        if outcome == "crash":
            raise RuntimeError("page crashed")
        if outcome == "not_verified":
            return PrepareResult.not_verified("Weave contact name does not match")
        if outcome == "ui_error":
            return PrepareResult.ui_error("New Message button not found")
        self.current = recipient
        return PrepareResult.ready()

    async def discard_draft(self) -> None:
        self.discarded += 1

    async def send_prepared_message(self, text: str) -> SendResult:
        outcome = self.outcomes.get(self.current.phone, "ok")
        if outcome == "send_crash":
            raise RuntimeError("browser died after clicking Send")
        self.sent.append(self.current.phone)
        if outcome == "not_delivered":
            return SendResult(SendStatus.NOT_DELIVERED, "Weave shows Not Delivered")
        if outcome == "unconfirmed":
            return SendResult(SendStatus.UNCONFIRMED, "Composer was not cleared")
        return SendResult(SendStatus.SENT)

    async def capture_screenshot(self) -> Optional[bytes]:
        return FAKE_PNG

    async def reset(self) -> None:
        self.resets += 1

    async def close(self) -> None:
        self.closed = True
