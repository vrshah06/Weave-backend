import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List

from config import (
    DATA_DIR,
    PROFILE_DIR,
    HEADLESS,
    SLOW_MO,
    WEAVE_EMAIL,
    WEAVE_PASSWORD,
)
from src.browser import BrowserManager
from src.deduplication import DeduplicationManager
from src.logging_utils import setup_logger, mask_phone, capture_screenshot
from src.messages import generate_message, hash_message
from src.models import Appointment, ProcessStatus, ProcessResult
from src.validation import validate_appointment_row
from src.weave import WeaveMessenger

logger = setup_logger("weave_main")


def ensure_sample_csv_exists(csv_file_path: Path) -> None:
    """
    Creates a sample CSV only when the requested file does not exist.
    In real use, replace it with your actual appointment export.
    """
    if csv_file_path.exists():
        return

    csv_file_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_file_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "patient_name",
                "phone",
                "appointment_date",
                "appointment_time",
            ]
        )
        writer.writerow(
            ["TEST PATIENT", "+17720000000", "09/21/2026", "10:00 AM"]
        )

    logger.info("Created sample CSV at %s", csv_file_path)


def parse_time_to_minutes(time_str: str) -> int:
    if not time_str:
        return 0
    clean_str = time_str.strip().upper()
    try:
        dt = datetime.strptime(clean_str, "%I:%M %p")
        return dt.hour * 60 + dt.minute
    except ValueError:
        try:
            dt = datetime.strptime(clean_str, "%H:%M")
            return dt.hour * 60 + dt.minute
        except ValueError:
            return 0


def load_appointments(csv_file_path: Path) -> List[Appointment]:
    if not csv_file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")

    appointments: List[Appointment] = []

    with csv_file_path.open(
        mode="r",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        reader = csv.DictReader(f)

        required = {
            "patient_name",
            "phone",
            "appointment_date",
            "appointment_time",
        }

        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"CSV is missing required columns: {', '.join(sorted(missing))}"
            )

        for idx, row in enumerate(reader, start=2):
            try:
                appointments.append(validate_appointment_row(row, idx))
            except ValueError as exc:
                logger.error("CSV row %d skipped: %s", idx, exc)

    # Sort appointments chronologically in ascending order (e.g. 8:15 AM -> 8:30 AM -> 4:15 PM)
    appointments.sort(key=lambda a: parse_time_to_minutes(a.appointment_time))

    return appointments


def authenticate_weave(weave: WeaveMessenger) -> bool:
    """
    Ensures that Weave is authenticated.

    1. Open Weave.
    2. Check the existing persistent session.
    3. If the session is expired, automatically log in.
    """

    # ---------------------------------------------------------
    # 1. Open Weave
    # ---------------------------------------------------------
    ok, status = weave.navigate_to_weave()

    if not ok:
        logger.error(
            "Could not open Weave: %s",
            status,
        )
        return False

    # ---------------------------------------------------------
    # 2. Check existing session
    # ---------------------------------------------------------
    logger.info("Checking existing Weave session...")

    authenticated, auth_status = weave.check_authenticated(
        timeout_ms=5000
    )

    if authenticated:
        logger.info(
            "Existing Weave session is active."
        )
        return True

    # ---------------------------------------------------------
    # 3. Automatic login
    # ---------------------------------------------------------
    logger.info(
        "No active Weave session found."
    )

    if not WEAVE_EMAIL or not WEAVE_PASSWORD:
        logger.error(
            "WEAVE_EMAIL or WEAVE_PASSWORD is missing "
            "from the environment/.env file."
        )
        return False

    logger.info(
        "Starting automatic Weave login..."
    )

    logged_in, login_status = weave.perform_auto_login(
        email=WEAVE_EMAIL,
        password=WEAVE_PASSWORD,
    )

    if logged_in:
        logger.info(
            "Automatic Weave authentication successful."
        )
        return True

    logger.error(
        "Automatic Weave authentication failed: %s",
        login_status,
    )

    return False


def process_appointments(
    csv_file_path: Path,
    is_send_mode: bool = False,
) -> None:
    logger.info("=" * 60)
    logger.info("WEAVE APPOINTMENT REMINDER AUTOMATION")
    logger.info(
        "MODE: %s",
        "PRODUCTION SEND" if is_send_mode else "DRY RUN",
    )
    logger.info("CSV: %s", csv_file_path)
    logger.info("=" * 60)

    appointments = load_appointments(csv_file_path)

    if not appointments:
        logger.error("No valid appointment rows found.")
        return

    logger.info("Loaded %d valid appointment(s).", len(appointments))
    logger.info("[EVENT] %s", json.dumps({"type": "LOADED_APPOINTMENTS", "total": len(appointments)}))

    dedup = DeduplicationManager()

    # BrowserManager already uses the persistent weave-profile directory.
    manager = BrowserManager(
        profile_dir=PROFILE_DIR,
        headless=HEADLESS,
        slow_mo=SLOW_MO,
    )

    context, page = manager.start()
    weave = WeaveMessenger(page)

    stats = {
        "sent": 0,
        "dry_run": 0,
        "already_sent": 0,
        "skipped": 0,
        "failed": 0,
    }

    try:
        # --------------------------------------------------------------
        # Authentication
        # --------------------------------------------------------------
        logger.info("[EVENT] %s", json.dumps({"type": "AUTH_START"}))
        if not authenticate_weave(weave):
            logger.info("[EVENT] %s", json.dumps({"type": "AUTH_FAILED"}))
            capture_screenshot(page, "authentication_failed")
            return
        logger.info("[EVENT] %s", json.dumps({"type": "AUTH_SUCCESS"}))

        # --------------------------------------------------------------
        # Process one patient at a time
        # --------------------------------------------------------------
        for position, appointment in enumerate(appointments, start=1):
            masked_phone = mask_phone(appointment.phone)

            logger.info("")
            logger.info(
                "[%d/%d] %s | phone %s",
                position,
                len(appointments),
                appointment.patient_name,
                masked_phone,
            )
            logger.info(
                "[EVENT] %s",
                json.dumps({
                    "type": "PATIENT_START",
                    "position": position,
                    "total": len(appointments),
                    "patient_name": appointment.patient_name,
                    "phone": masked_phone,
                })
            )

            # 1. Duplicate prevention
            if dedup.is_already_sent(appointment):
                logger.info("SKIP_ALREADY_SENT")
                logger.info(
                    "[EVENT] %s",
                    json.dumps({
                        "type": "PATIENT_SKIPPED",
                        "patient_name": appointment.patient_name,
                        "reason": "Already sent today"
                    })
                )
                stats["already_sent"] += 1
                continue

            try:
                # 2. Messages
                ok, status = weave.open_messages()
                if not ok:
                    logger.error("Failed to open Messages for patient %s: %s", appointment.patient_name, status.value)
                    capture_screenshot(page, f"row_{appointment.row_index}_messages_{status.value}", appointment.row_index)
                    stats["failed"] += 1
                    continue

                # 3. New Message
                ok, status = weave.open_new_message()
                if not ok:
                    logger.error("Failed to open New Message for patient %s: %s", appointment.patient_name, status.value)
                    capture_screenshot(page, f"row_{appointment.row_index}_new_msg_{status.value}", appointment.row_index)
                    stats["failed"] += 1
                    continue

                # 4. Search phone
                ok, status, results = weave.search_recipient(
                    appointment.phone
                )
                if not ok:
                    dedup.log_result(
                        ProcessResult(
                            appointment=appointment,
                            status=status,
                            error="Recipient search failed",
                            timestamp=datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        )
                    )
                    logger.info("[EVENT] %s", json.dumps({"type": "PATIENT_SKIPPED", "patient_name": appointment.patient_name, "phone": masked_phone, "reason": "Recipient search failed"}))
                    stats["skipped"] += 1
                    capture_screenshot(
                        page,
                        f"row_{appointment.row_index}_search_{status.value}",
                        appointment.row_index,
                    )
                    continue

                logger.info(
                    "Search returned %d candidate(s).",
                    len(results),
                )

                # 5. Select ONLY a verified patient card
                ok, status, reason = weave.select_recipient(
                    appointment.phone,
                    appointment.patient_name,
                )

                if not ok:
                    logger.error(
                        "Recipient not selected: %s | %s",
                        status.value,
                        reason,
                    )

                    dedup.log_result(
                        ProcessResult(
                            appointment=appointment,
                            status=status,
                            error=reason,
                            timestamp=datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        )
                    )

                    logger.info("[EVENT] %s", json.dumps({"type": "PATIENT_SKIPPED", "patient_name": appointment.patient_name, "phone": masked_phone, "reason": reason or "Recipient selection failed"}))
                    stats["skipped"] += 1
                    capture_screenshot(
                        page,
                        f"row_{appointment.row_index}_recipient_{status.value}",
                        appointment.row_index,
                    )
                    continue


                logger.info("Recipient selected and verified.")

                # 6. Wait for conversation and verify recipient again
                ok, status = weave.wait_for_conversation(
                    expected_phone=appointment.phone,
                    expected_patient_name=appointment.patient_name,
                )

                if not ok:
                    logger.error(
                        "Conversation verification failed: %s",
                        status.value,
                    )

                    dedup.log_result(
                        ProcessResult(
                            appointment=appointment,
                            status=status,
                            error="Conversation recipient could not be verified",
                            timestamp=datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        )
                    )

                    stats["failed"] += 1
                    capture_screenshot(
                        page,
                        f"row_{appointment.row_index}_conversation_{status.value}",
                        appointment.row_index,
                    )
                    continue

                # 7. Generate deterministic reminder
                message_text = generate_message(
                    patient_name=appointment.patient_name,
                    appointment_date=appointment.appointment_date,
                    appointment_time=appointment.appointment_time,
                )
                message_hash = hash_message(message_text)

                logger.info(
                    "COMPOSED MESSAGE FOR %s:\n----------------------------------------\n%s\n----------------------------------------",
                    appointment.patient_name,
                    message_text,
                )

                # 8. Compose
                ok, status = weave.enter_message(message_text)

                if not ok:
                    logger.error(
                        "Message composition failed: %s",
                        status.value,
                    )

                    dedup.log_result(
                        ProcessResult(
                            appointment=appointment,
                            status=status,
                            error="Message composition failed",
                            message_hash=message_hash,
                            timestamp=datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        )
                    )

                    stats["failed"] += 1
                    capture_screenshot(
                        page,
                        f"row_{appointment.row_index}_compose_{status.value}",
                        appointment.row_index,
                    )
                    continue

                # 9. Verify exact composer contents + Send button
                ok, status = weave.verify_ready_to_send()

                if not ok:
                    logger.error(
                        "Pre-send verification failed: %s",
                        status.value,
                    )

                    dedup.log_result(
                        ProcessResult(
                            appointment=appointment,
                            status=status,
                            error="Pre-send verification failed",
                            message_hash=message_hash,
                            timestamp=datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        )
                    )

                    stats["failed"] += 1
                    capture_screenshot(
                        page,
                        f"row_{appointment.row_index}_ready_{status.value}",
                        appointment.row_index,
                    )
                    continue

                # ------------------------------------------------------
                # DRY RUN — PAUSE TO VISUALLY SEE TYPED MESSAGE
                # ------------------------------------------------------
                if not is_send_mode:
                    logger.info(
                        "DRY RUN — Message composed and visible in chat section for %s.",
                        appointment.patient_name
                    )
                    logger.info("Pausing 1 second to visually verify the typed message in the browser window...")
                    time.sleep(1.0)

                    dedup.log_result(
                        ProcessResult(
                            appointment=appointment,
                            status=ProcessStatus.READY_TO_SEND,
                            message_hash=message_hash,
                            timestamp=datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        )
                    )

                    stats["dry_run"] += 1
                    logger.info("[EVENT] %s", json.dumps({"type": "MESSAGE_DRY_RUN", "patient_name": appointment.patient_name, "phone": masked_phone}))
                    continue

                # ------------------------------------------------------
                # PRODUCTION SEND
                # ------------------------------------------------------
                ok, send_status, fail_reason = weave.send_message(
                    message_text=message_text
                )

                if ok and send_status == ProcessStatus.SENT:
                    logger.info("SENT — outgoing message verified and delivered.")
                    logger.info("[EVENT] %s", json.dumps({"type": "MESSAGE_SENT", "patient_name": appointment.patient_name, "phone": masked_phone}))

                    dedup.log_result(
                        ProcessResult(
                            appointment=appointment,
                            status=ProcessStatus.SENT,
                            message_hash=message_hash,
                            timestamp=datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        )
                    )

                    stats["sent"] += 1
                else:
                    err_msg = fail_reason or f"Message not delivered ({send_status.value})"
                    logger.error(
                        "MESSAGE NOT DELIVERED / FAILED — %s: %s",
                        send_status.value,
                        err_msg,
                    )
                    logger.info("[EVENT] %s", json.dumps({"type": "PATIENT_FAILED", "patient_name": appointment.patient_name, "phone": masked_phone, "reason": err_msg}))

                    dedup.log_result(
                        ProcessResult(
                            appointment=appointment,
                            status=send_status if send_status in (ProcessStatus.FAILED, ProcessStatus.NOT_DELIVERED) else ProcessStatus.FAILED,
                            error=err_msg,
                            message_hash=message_hash,
                            timestamp=datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        )
                    )

                    stats["failed"] += 1
                    capture_screenshot(
                        page,
                        f"row_{appointment.row_index}_send_{send_status.value}",
                        appointment.row_index,
                    )

            except Exception as exc:
                logger.exception(
                    "Unexpected error for row %d: %s",
                    appointment.row_index,
                    exc,
                )
                logger.info("[EVENT] %s", json.dumps({"type": "PATIENT_SKIPPED", "patient_name": appointment.patient_name, "phone": masked_phone, "reason": f"Incomplete processing ({str(exc)})"}))
                stats["skipped"] += 1


                stats["failed"] += 1

                capture_screenshot(
                    page,
                    f"row_{appointment.row_index}_unexpected_error",
                    appointment.row_index,
                )

                try:
                    dedup.log_result(
                        ProcessResult(
                            appointment=appointment,
                            status=ProcessStatus.FAILED,
                            error=str(exc)[:500],
                            timestamp=datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        )
                    )
                except Exception:
                    pass

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
        logger.info("[EVENT] %s", json.dumps({"type": "RUN_COMPLETE", "stats": stats, "total": len(appointments)}))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Weave Appointment Reminder Automation"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare and verify reminders without clicking Send.",
    )

    parser.add_argument(
        "--send",
        action="store_true",
        help="Enable actual message sending.",
    )

    parser.add_argument(
        "--file",
        type=str,
        default=str(DATA_DIR / "appointments.csv"),
        help="Appointment CSV path.",
    )

    args = parser.parse_args()

    if args.dry_run and args.send:
        parser.error("--dry-run and --send cannot be used together.")

    csv_path = Path(args.file)

    # Safe default: without --send, NEVER click Send.
    if args.send:
        process_appointments(csv_path, is_send_mode=True)
    else:
        process_appointments(csv_path, is_send_mode=False)


if __name__ == "__main__":
    main()
