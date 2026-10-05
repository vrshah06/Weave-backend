import logging
from datetime import date
from typing import Callable, Optional

from bson import ObjectId

from automation.driver import DriverError, MessagingDriver, PrepareFailure, Recipient, SendStatus
from models.enums import AppointmentStatus, RunItemStatus, RunMode, RunStatus
from repositories import appointment_repository, run_item_repository, run_repository, screenshot_repository
from services import settings_service
from services.message_template import render_message
from utils.clock import utc_now
from utils.phone import mask_phone
from utils.schedule import format_time_12h
from worker.run_logger import RunLogger

logger = logging.getLogger("weave.worker")

COUNT_FIELD = {
    RunItemStatus.DRY_RUN_VERIFIED: "dry_run_verified",
    RunItemStatus.SENT: "sent",
    RunItemStatus.FAILED: "failed",
    RunItemStatus.SKIPPED: "skipped",
    RunItemStatus.NEEDS_REVIEW: "needs_review",
}
SUCCESS_STATUSES = (RunItemStatus.DRY_RUN_VERIFIED, RunItemStatus.SENT)


class RunExecutor:
    def __init__(
        self,
        run: dict,
        driver: MessagingDriver,
        *,
        sending_enabled: bool,
        max_consecutive_errors: int,
        shutdown_requested: Callable[[], bool] = lambda: False,
    ):
        self.run = run
        self.run_id: ObjectId = run["_id"]
        self.mode = RunMode(run["mode"])
        self.appointment_date = date.fromisoformat(run["appointment_date"])
        self.driver = driver
        self.sending_enabled = sending_enabled
        self.max_consecutive_errors = max_consecutive_errors
        self.shutdown_requested = shutdown_requested
        self.consecutive_errors = 0
        self.failure_screenshot: Optional[bytes] = None
        self.log = RunLogger(self.run_id)

    async def execute(self) -> RunStatus:
        await self.log.info("run.started", f"{self.mode.value} run started for {self.appointment_date.isoformat()}")
        try:
            return await self._execute()
        except DriverError as exc:
            return await self._finish(RunStatus.FAILED, f"Browser error: {exc}")
        except Exception as exc:
            logger.exception("Run %s crashed", self.run_id)
            return await self._finish(RunStatus.FAILED, f"Unexpected worker error: {exc}")
        finally:
            try:
                await self.driver.close()
            except Exception:
                logger.exception("Could not close the browser for run %s", self.run_id)

    async def _execute(self) -> RunStatus:
        settings = await settings_service.get_settings()
        appointments = await appointment_repository.list_runnable_with_patient(self.appointment_date)
        await run_repository.set_total(self.run_id, len(appointments))
        if not appointments:
            return await self._finish(RunStatus.COMPLETED, None, "No pending appointments were left to process")

        await self.log.info("browser.starting", f"Starting browser for {len(appointments)} appointment(s)")
        await self.driver.start()
        await self.driver.authenticate()
        await self.log.info("browser.authenticated", "Signed in to Weave")

        for appointment in appointments:
            if self.shutdown_requested():
                return await self._finish(RunStatus.INTERRUPTED, "Worker shut down before the run finished; remaining appointments are still PENDING")
            if await run_repository.is_stop_requested(self.run_id):
                return await self._finish(RunStatus.STOPPED, None, "Stopped on request; remaining appointments are still PENDING")
            await self._process(appointment, settings)
            if self.consecutive_errors >= self.max_consecutive_errors:
                return await self._finish(RunStatus.FAILED, f"Stopped after {self.consecutive_errors} consecutive browser errors; Weave may be unavailable")
        return await self._finish(RunStatus.COMPLETED, None)

    async def _finish(self, status: RunStatus, error: Optional[str], note: Optional[str] = None) -> RunStatus:
        await run_repository.finish(self.run_id, status, error)
        message = error or note or f"Run {status.value.lower()}"
        if status in (RunStatus.FAILED, RunStatus.INTERRUPTED):
            await self.log.error("run.finished", f"Run {status.value}: {message}")
        else:
            await self.log.info("run.finished", f"Run {status.value}: {message}")
        return status

    async def _process(self, appointment: dict, settings: dict) -> None:
        patient = appointment["patient"]
        appointment_id = appointment["_id"]
        item_id = await run_item_repository.start(self.run_id, appointment_id, patient["_id"])
        await self.log.info(
            "patient.started",
            f"{patient['full_name']} ({mask_phone(patient['phone'])}) at {format_time_12h(appointment['appointment_time'])}",
            appointment_id,
        )

        self.failure_screenshot = None
        status, reason = await self._attempt(appointment, settings)

        screenshot_id = None
        if self.failure_screenshot and status not in SUCCESS_STATUSES:
            screenshot_id = await self._save_screenshot(item_id, status, self.failure_screenshot)
        await run_item_repository.finish(item_id, status, reason, screenshot_id)
        await run_repository.record_outcome(self.run_id, COUNT_FIELD[status])

        message = f"{patient['full_name']}: {status.value}" + (f" ({reason})" if reason else "")
        if status in SUCCESS_STATUSES:
            await self.log.info("patient.finished", message, appointment_id)
        else:
            await self.log.warning("patient.finished", message, appointment_id)

    async def _attempt(self, appointment: dict, settings: dict) -> tuple[RunItemStatus, Optional[str]]:
        appointment_id = appointment["_id"]
        current = await appointment_repository.find_by_id(appointment_id)
        if current is None or current["status"] != AppointmentStatus.PENDING.value or current.get("excluded"):
            state = "excluded" if current and current.get("excluded") else (current or {}).get("status", "deleted")
            return RunItemStatus.SKIPPED, f"Appointment became {state} before processing"

        patient = appointment["patient"]
        recipient = Recipient(patient["full_name"], patient["first_name"], patient["last_name"], patient["phone"])
        text = render_message(
            settings["message_template"],
            patient=patient,
            appointment_date=self.appointment_date,
            appointment_time=appointment["appointment_time"],
            provider=appointment.get("provider", ""),
            business_name=settings["business_name"],
        )

        try:
            prepared = await self.driver.prepare_message(recipient, text)
        except Exception as exc:
            self.consecutive_errors += 1
            await self._capture_failure()
            await self._reset_driver()
            return await self._fail_before_send(appointment_id, RunItemStatus.FAILED, f"Browser error while preparing: {exc}")

        if not prepared.ok:
            await self._capture_failure()
            await self._discard_draft(appointment_id)
            if prepared.failure is PrepareFailure.UI_ERROR:
                self.consecutive_errors += 1
                await self._reset_driver()
                return await self._fail_before_send(appointment_id, RunItemStatus.FAILED, prepared.reason)
            self.consecutive_errors = 0
            return await self._fail_before_send(appointment_id, RunItemStatus.SKIPPED, prepared.reason)

        self.consecutive_errors = 0
        if self.mode is RunMode.DRY_RUN:
            await self._discard_draft(appointment_id)
            return RunItemStatus.DRY_RUN_VERIFIED, None

        if not await appointment_repository.claim_for_sending(appointment_id, self.run_id):
            await self._discard_draft(appointment_id)
            return RunItemStatus.SKIPPED, "Appointment changed just before sending"

        try:
            result = await self.driver.send_prepared_message(text)
        except Exception as exc:
            await self._capture_failure()
            reason = f"Browser error after clicking Send; check Weave before re-sending: {exc}"
            await appointment_repository.set_status(appointment_id, AppointmentStatus.NEEDS_REVIEW, reason, self.run_id)
            return RunItemStatus.NEEDS_REVIEW, reason

        if result.status is not SendStatus.SENT:
            await self._capture_failure()
        if result.status is SendStatus.SENT:
            await appointment_repository.set_status(appointment_id, AppointmentStatus.SENT, None, self.run_id, {"sent_at": utc_now()})
            return RunItemStatus.SENT, None
        if result.status is SendStatus.NOT_DELIVERED:
            await appointment_repository.set_status(appointment_id, AppointmentStatus.FAILED, result.reason, self.run_id)
            return RunItemStatus.FAILED, result.reason
        reason = result.reason or "Could not confirm the message was sent; check Weave"
        await appointment_repository.set_status(appointment_id, AppointmentStatus.NEEDS_REVIEW, reason, self.run_id)
        return RunItemStatus.NEEDS_REVIEW, reason

    async def _fail_before_send(self, appointment_id: ObjectId, status: RunItemStatus, reason: Optional[str]) -> tuple[RunItemStatus, Optional[str]]:
        # Dry runs never change appointment status.
        if self.mode is RunMode.SEND:
            await appointment_repository.set_status(appointment_id, AppointmentStatus(status.value), reason, self.run_id)
        return status, reason

    async def _discard_draft(self, appointment_id: Optional[ObjectId] = None) -> None:
        try:
            await self.driver.discard_draft()
        except Exception as exc:
            await self.log.warning("draft.not_cleared", f"Draft may remain in Weave Drafts: {exc}", appointment_id)

    async def _reset_driver(self) -> None:
        try:
            await self.driver.reset()
        except Exception:
            logger.warning("Could not reset the browser for run %s", self.run_id, exc_info=True)

    async def _capture_failure(self) -> None:
        try:
            self.failure_screenshot = await self.driver.capture_screenshot()
        except Exception:
            logger.warning("Could not capture a screenshot for run %s", self.run_id, exc_info=True)

    async def _save_screenshot(self, item_id: ObjectId, status: RunItemStatus, content: bytes) -> Optional[ObjectId]:
        try:
            return await screenshot_repository.save(self.run_id, item_id, status.value.lower(), content)
        except Exception:
            logger.warning("Could not save a screenshot for run %s", self.run_id, exc_info=True)
            return None
