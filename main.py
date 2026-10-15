import argparse
import asyncio
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from automation.weave_driver import WeaveDriver
from core import database
from core.config import config
from core.logging import configure_logging
from models.enums import RunMode, RunStatus
from repositories import appointment_repository, run_repository
from services import import_service, settings_service
from utils.appointment_csv import AppointmentRow, decode_csv_bytes, parse_appointment_csv
from utils.schedule import parse_appointment_date
from worker.run_executor import RunExecutor

logger = logging.getLogger("weave.cli")


def load_appointments(csv_file_path: Path) -> List[AppointmentRow]:
    """
    Load and parse appointment records from a CSV file.
    Validates CSV format, required columns, and patient data.
    """
    if not csv_file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")

    content = csv_file_path.read_bytes()
    parsed = parse_appointment_csv(decode_csv_bytes(content))
    logger.info("Loaded %d valid appointment row(s) from %s", len(parsed.rows), csv_file_path.name)
    if parsed.errors:
        for err in parsed.errors:
            logger.warning("CSV row %d error: %s", err.row_number, err.message)
    return parsed.rows


async def authenticate_weave(driver: WeaveDriver) -> bool:
    """
    Ensure the Playwright browser is started and authenticated with Weave.
    Reuses existing session cookies or logs in automatically using configured credentials.
    """
    logger.info("Starting browser and verifying Weave authentication...")
    await driver.start()
    await driver.authenticate()
    logger.info("Weave authentication successful.")
    return True


async def process_appointments(
    csv_file_path: Optional[Path] = None,
    is_send_mode: bool = False,
    target_date: Optional[date] = None,
) -> int:
    """
    Process appointments sequentially with strictly single-recipient sending.
    Supports both Dry Run and Send modes, syncing to MongoDB and Weave.
    """
    database.connect()
    await database.ensure_indexes()

    mode = RunMode.SEND if is_send_mode else RunMode.DRY_RUN
    logger.info("=" * 60)
    logger.info("WEAVE APPOINTMENT REMINDER AUTOMATION")
    logger.info("MODE: %s", "PRODUCTION SEND" if is_send_mode else "DRY RUN")
    if csv_file_path:
        logger.info("CSV:  %s", csv_file_path)
    logger.info("=" * 60)

    # 1. Load appointments from CSV if file provided
    if csv_file_path and csv_file_path.exists():
        load_appointments(csv_file_path)
        content = csv_file_path.read_bytes()
        try:
            import_doc = await import_service.import_appointments(csv_file_path.name, content)
            logger.info("Database synchronized: %s", import_doc["counts"])
            if not target_date and import_doc.get("dates"):
                target_date = date.fromisoformat(import_doc["dates"][0])
        except Exception as exc:
            logger.error("Failed to synchronize appointments to database: %s", exc)
            return 1

    settings = await settings_service.get_settings()
    tz = ZoneInfo(settings.get("time_zone", "America/New_York"))
    today = datetime.now(tz).date()

    if target_date is None:
        dates_with_pending = await appointment_repository.list_dates_with_pending()
        if dates_with_pending:
            target_date = dates_with_pending[0]
        else:
            target_date = today

    logger.info("Target appointment date: %s", target_date.isoformat())

    runnable_count = await appointment_repository.count_runnable(target_date)
    if runnable_count == 0:
        logger.warning("No pending, non-excluded appointments found for date %s", target_date.isoformat())
        return 0

    logger.info("Found %d pending appointment(s) to process", runnable_count)

    # 2. Initialize run in database
    run_doc = await run_repository.create(target_date, mode)
    claimed_run = await run_repository.claim_next_queued(f"cli-{mode.value.lower()}")
    run_to_execute = claimed_run or run_doc

    # 3. Initialize driver and execute sequential single-recipient workflow
    driver = WeaveDriver()
    try:
        await authenticate_weave(driver)
        executor = RunExecutor(
            run=run_to_execute,
            driver=driver,
            sending_enabled=(mode == RunMode.SEND),
            max_consecutive_errors=config.worker_max_consecutive_errors,
        )
        # RunExecutor executes the strictly sequential processing loop
        final_status = await executor.execute()
    finally:
        await driver.close()

    final_run = await run_repository.find_by_id(run_to_execute["_id"])
    counts = (final_run or {}).get("counts", {})

    print("\n" + "=" * 60)
    print("WEAVE REMINDER AUTOMATION SUMMARY")
    print("=" * 60)
    print(f"Date:         {target_date.isoformat()}")
    print(f"Mode:         {mode.value}")
    print(f"Status:       {final_status.value}")
    print(f"Total:        {counts.get('total', 0)}")
    print(f"Verified:     {counts.get('dry_run_verified', 0)}")
    print(f"Sent:         {counts.get('sent', 0)}")
    print(f"Failed:       {counts.get('failed', 0)}")
    print(f"Skipped:      {counts.get('skipped', 0)}")
    print("=" * 60 + "\n")

    return 0 if final_status in (RunStatus.COMPLETED, RunStatus.STOPPED) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Weave Appointment Reminder Automation CLI")
    parser.add_argument("--dry-run", action="store_true", help="Dry run: verify appointments and message composer without clicking Send.")
    parser.add_argument("--send", action="store_true", help="Send mode: actually send SMS messages in Weave.")
    parser.add_argument("--date", type=str, default=None, help="Target appointment date (YYYY-MM-DD or MM/DD/YYYY).")
    parser.add_argument("--file", type=str, default="data/appointments.csv", help="Path to appointments CSV file.")
    args = parser.parse_args()

    if args.dry_run and args.send:
        parser.error("--dry-run and --send cannot be used together.")

    # Default to dry-run if neither specified
    if not args.send and not args.dry_run:
        args.dry_run = True

    target_date = None
    if args.date:
        try:
            target_date = parse_appointment_date(args.date)
        except Exception as exc:
            logger.error("Invalid --date argument: %s", exc)
            sys.exit(1)

    csv_path = Path(args.file) if args.file else None

    configure_logging(config.log_level)
    try:
        sys.exit(
            asyncio.run(
                process_appointments(
                    csv_file_path=csv_path,
                    is_send_mode=args.send,
                    target_date=target_date,
                )
            )
        )
    finally:
        database.close()


if __name__ == "__main__":
    main()
