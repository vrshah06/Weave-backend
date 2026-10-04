import argparse
import csv
import json
import time
from pathlib import Path
from typing import List

from core.config import DATA_DIR, PROFILE_DIR, HEADLESS, SLOW_MO, WEAVE_EMAIL, WEAVE_PASSWORD
from automation.browser_manager import BrowserManager
from automation.deduplication import DeduplicationManager
from automation.logging_utils import setup_logger, mask_phone, capture_screenshot
from automation.message_templates import generate_message, hash_message
from automation.models import Appointment, ProcessStatus, ProcessResult
from automation.validation import validate_appointment_row
from automation.weave_messenger import WeaveMessenger
from utils.formatters import parse_time_to_minutes

logger = setup_logger("weave_main")

REQUIRED_COLUMNS = {"patient_name", "phone", "appointment_date", "appointment_time"}


def emit_event(event_type: str, **fields) -> None:
    # Parsed from stdout by services/automation_runner.py
    logger.info("[EVENT] %s", json.dumps({"type": event_type, **fields}))


def load_appointments(csv_file_path: Path) -> List[Appointment]:
    if not csv_file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")

    appointments: List[Appointment] = []
    with csv_file_path.open(mode="r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

        for idx, row in enumerate(reader, start=2):
            try:
                appointments.append(validate_appointment_row(row, idx))
            except ValueError as exc:
                logger.error("CSV row %d skipped: %s", idx, exc)

    appointments.sort(key=lambda a: parse_time_to_minutes(a.appointment_time))
    return appointments


def authenticate_weave(weave: WeaveMessenger) -> bool:
    ok, status = weave.navigate_to_weave()
    if not ok:
        logger.error("Could not open Weave: %s", status)
        return False

    logger.info("Checking existing Weave session...")
    authenticated, _ = weave.check_authenticated(timeout_ms=5000)
    if authenticated:
        logger.info("Existing Weave session is active.")
        return True

    logger.info("No active Weave session found.")
    if not WEAVE_EMAIL or not WEAVE_PASSWORD:
        logger.error("WEAVE_EMAIL or WEAVE_PASSWORD is missing from the environment/.env file.")
        return False

    logger.info("Starting automatic Weave login...")
    logged_in, login_status = weave.perform_auto_login(email=WEAVE_EMAIL, password=WEAVE_PASSWORD)
    if logged_in:
        logger.info("Automatic Weave authentication successful.")
        return True

    logger.error("Automatic Weave authentication failed: %s", login_status)
    return False


def process_appointments(csv_file_path: Path, is_send_mode: bool = False) -> None:
    logger.info("=" * 60)
    logger.info("WEAVE APPOINTMENT REMINDER AUTOMATION")
    logger.info("MODE: %s", "PRODUCTION SEND" if is_send_mode else "DRY RUN")
    logger.info("CSV: %s", csv_file_path)
    logger.info("=" * 60)

    appointments = load_appointments(csv_file_path)
    if not appointments:
        logger.error("No valid appointment rows found.")
        return

    logger.info("Loaded %d valid appointment(s).", len(appointments))
    emit_event("LOADED_APPOINTMENTS", total=len(appointments))

    dedup = DeduplicationManager()
    manager = BrowserManager(profile_dir=PROFILE_DIR, headless=HEADLESS, slow_mo=SLOW_MO)
    context, page = manager.start()
    weave = WeaveMessenger(page)

    stats = {"sent": 0, "dry_run": 0, "already_sent": 0, "skipped": 0, "failed": 0}

    def record_outcome(appointment, event_type, stat, *, status=None, error=None,
                       message_hash=None, screenshot=None, **event_fields):
        if status is not None:
            dedup.log_result(ProcessResult(appointment=appointment, status=status, error=error, message_hash=message_hash))
        emit_event(event_type, patient_name=appointment.patient_name, **event_fields)
        stats[stat] += 1
        if screenshot:
            capture_screenshot(page, f"row_{appointment.row_index}_{screenshot}", appointment.row_index)

    try:
        emit_event("AUTH_START")
        if not authenticate_weave(weave):
            emit_event("AUTH_FAILED")
            capture_screenshot(page, "authentication_failed")
            return
        emit_event("AUTH_SUCCESS")

        for position, appointment in enumerate(appointments, start=1):
            masked_phone = mask_phone(appointment.phone)

            logger.info("")
            logger.info("[%d/%d] %s | phone %s", position, len(appointments), appointment.patient_name, masked_phone)
            emit_event("PATIENT_START", position=position, total=len(appointments),
                       patient_name=appointment.patient_name, phone=masked_phone)

            if dedup.is_already_sent(appointment):
                logger.info("SKIP_ALREADY_SENT")
                record_outcome(appointment, "PATIENT_SKIPPED", "already_sent", reason="Already sent today")
                continue

            try:
                ok, status = weave.open_messages()
                if not ok:
                    logger.error("Failed to open Messages for patient %s: %s", appointment.patient_name, status.value)
                    record_outcome(appointment, "PATIENT_FAILED", "failed", screenshot=f"messages_{status.value}",
                                   phone=masked_phone, reason=f"Failed to open Messages ({status.value})")
                    continue

                ok, status = weave.open_new_message()
                if not ok:
                    logger.error("Failed to open New Message for patient %s: %s", appointment.patient_name, status.value)
                    record_outcome(appointment, "PATIENT_FAILED", "failed", screenshot=f"new_msg_{status.value}",
                                   phone=masked_phone, reason=f"Failed to open New Message ({status.value})")
                    continue

                ok, status, results = weave.search_recipient(appointment.phone)
                if not ok:
                    record_outcome(appointment, "PATIENT_SKIPPED", "skipped", status=status,
                                   error="Recipient search failed", screenshot=f"search_{status.value}",
                                   phone=masked_phone, reason="Recipient search failed")
                    continue
                logger.info("Search returned %d candidate(s).", len(results))

                ok, status, reason = weave.select_recipient(appointment.phone, appointment.patient_name)
                if not ok:
                    logger.error("Recipient not selected: %s | %s", status.value, reason)
                    record_outcome(appointment, "PATIENT_SKIPPED", "skipped", status=status, error=reason,
                                   screenshot=f"recipient_{status.value}",
                                   phone=masked_phone, reason=reason or "Recipient selection failed")
                    continue
                logger.info("Recipient selected and verified.")

                ok, status = weave.wait_for_conversation(
                    expected_phone=appointment.phone,
                    expected_patient_name=appointment.patient_name,
                )
                if not ok:
                    logger.error("Conversation verification failed: %s", status.value)
                    record_outcome(appointment, "PATIENT_FAILED", "failed", status=status,
                                   error="Conversation recipient could not be verified",
                                   screenshot=f"conversation_{status.value}",
                                   phone=masked_phone, reason=f"Conversation verification failed ({status.value})")
                    continue

                message_text = generate_message(
                    patient_name=appointment.patient_name,
                    appointment_date=appointment.appointment_date,
                    appointment_time=appointment.appointment_time,
                )
                message_hash = hash_message(message_text)
                logger.info(
                    "COMPOSED MESSAGE FOR %s:\n%s\n%s\n%s",
                    appointment.patient_name, "-" * 40, message_text, "-" * 40,
                )

                ok, status = weave.enter_message(message_text)
                if not ok:
                    logger.error("Message composition failed: %s", status.value)
                    record_outcome(appointment, "PATIENT_FAILED", "failed", status=status,
                                   error="Message composition failed", message_hash=message_hash,
                                   screenshot=f"compose_{status.value}",
                                   phone=masked_phone, reason=f"Message composition failed ({status.value})")
                    continue

                ok, status = weave.verify_ready_to_send()
                if not ok:
                    logger.error("Pre-send verification failed: %s", status.value)
                    record_outcome(appointment, "PATIENT_FAILED", "failed", status=status,
                                   error="Pre-send verification failed", message_hash=message_hash,
                                   screenshot=f"ready_{status.value}",
                                   phone=masked_phone, reason=f"Pre-send verification failed ({status.value})")
                    continue

                if not is_send_mode:
                    logger.info("DRY RUN — Message composed and visible in chat section for %s.", appointment.patient_name)
                    logger.info("Pausing 1 second to visually verify the typed message in the browser window...")
                    time.sleep(1.0)
                    record_outcome(appointment, "MESSAGE_DRY_RUN", "dry_run", status=ProcessStatus.READY_TO_SEND,
                                   message_hash=message_hash, phone=masked_phone)
                    continue

                ok, send_status, fail_reason = weave.send_message(message_text=message_text)
                if ok and send_status == ProcessStatus.SENT:
                    logger.info("SENT — outgoing message verified and delivered.")
                    record_outcome(appointment, "MESSAGE_SENT", "sent", status=ProcessStatus.SENT,
                                   message_hash=message_hash, phone=masked_phone)
                else:
                    err_msg = fail_reason or f"Message not delivered ({send_status.value})"
                    logger.error("MESSAGE NOT DELIVERED / FAILED — %s: %s", send_status.value, err_msg)
                    logged_status = send_status if send_status in (ProcessStatus.FAILED, ProcessStatus.NOT_DELIVERED) else ProcessStatus.FAILED
                    record_outcome(appointment, "PATIENT_FAILED", "failed", status=logged_status,
                                   error=err_msg, message_hash=message_hash,
                                   screenshot=f"send_{send_status.value}",
                                   phone=masked_phone, reason=err_msg)

            except Exception as exc:
                logger.exception("Unexpected error for row %d: %s", appointment.row_index, exc)
                record_outcome(appointment, "PATIENT_SKIPPED", "skipped", screenshot="unexpected_error",
                               phone=masked_phone, reason=f"Incomplete processing ({str(exc)})")
                stats["failed"] += 1
                try:
                    dedup.log_result(ProcessResult(appointment=appointment, status=ProcessStatus.FAILED, error=str(exc)[:500]))
                except Exception:
                    logger.exception("Could not write failure for row %d to the reminder log", appointment.row_index)

    finally:
        manager.close()

        logger.info("")
        logger.info("=" * 60)
        logger.info("AUTOMATION RUN COMPLETE")
        logger.info("=" * 60)
        logger.info("Total:        %d", len(appointments))
        logger.info("Sent:         %d", stats["sent"])
        logger.info("Dry run:      %d", stats["dry_run"])
        logger.info("Already sent: %d", stats["already_sent"])
        logger.info("Skipped:      %d", stats["skipped"])
        logger.info("Failed:       %d", stats["failed"])
        logger.info("=" * 60)
        emit_event("RUN_COMPLETE", stats=stats, total=len(appointments))


def main() -> None:
    parser = argparse.ArgumentParser(description="Weave Appointment Reminder Automation")
    parser.add_argument("--dry-run", action="store_true", help="Prepare and verify reminders without clicking Send.")
    parser.add_argument("--send", action="store_true", help="Enable actual message sending.")
    parser.add_argument("--file", type=str, default=str(DATA_DIR / "appointments.csv"), help="Appointment CSV path.")
    args = parser.parse_args()

    if args.dry_run and args.send:
        parser.error("--dry-run and --send cannot be used together.")

    # Without --send, Send is never clicked.
    process_appointments(Path(args.file), is_send_mode=args.send)


if __name__ == "__main__":
    main()
