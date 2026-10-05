"""
One-time import of the legacy logs/reminder_log.csv so the new system knows which reminders
were already sent (SENT) or possibly sent (SEND_UNCONFIRMED -> NEEDS_REVIEW).

Usage:
    python -m scripts.seed_sent_history                 # report only
    python -m scripts.seed_sent_history --apply         # write to MONGODB_URI
"""
import argparse
import asyncio
import csv
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core import database
from core.config import BASE_DIR, config
from core.logging import configure_logging
from models.enums import AppointmentStatus
from repositories import appointment_repository, import_repository, patient_repository
from utils.names import parse_patient_name
from utils.phone import normalize_phone
from utils.schedule import parse_appointment_date, parse_appointment_time

logger = logging.getLogger("weave.seed")

LEGACY_STATUS_MAP = {"SENT": AppointmentStatus.SENT, "SEND_UNCONFIRMED": AppointmentStatus.NEEDS_REVIEW}
UPGRADEABLE = (AppointmentStatus.PENDING.value, AppointmentStatus.FAILED.value, AppointmentStatus.SKIPPED.value, AppointmentStatus.CANCELLED.value)


def read_legacy_rows(path: Path) -> tuple[dict, list[str]]:
    slots: dict[tuple, dict] = {}
    problems = []
    with path.open(encoding="utf-8") as f:
        for line_number, row in enumerate(csv.DictReader(f), start=2):
            status = LEGACY_STATUS_MAP.get(row.get("status", "").strip())
            if status is None:
                continue
            try:
                patient = parse_patient_name(row["patient_name"])
                phone = normalize_phone(row["phone"])
                slot = (patient.name_key, phone, parse_appointment_date(row["appointment_date"]), parse_appointment_time(row["appointment_time"]))
            except ValueError as exc:
                problems.append(f"line {line_number}: {exc}")
                continue
            current = slots.get(slot)
            if current is None or status is AppointmentStatus.SENT:
                slots[slot] = {"patient": patient, "phone": phone, "phone_raw": row["phone"], "status": status, "timestamp": row.get("timestamp", "")}
    return slots, problems


def parse_legacy_timestamp(value: str, time_zone: str):
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo(time_zone))
    except ValueError:
        return None


async def seed(path: Path, apply: bool) -> None:
    slots, problems = read_legacy_rows(path)
    for problem in problems:
        logger.warning("Skipped %s", problem)
    by_status = {s: sum(1 for v in slots.values() if v["status"] is s) for s in LEGACY_STATUS_MAP.values()}
    logger.info("Legacy log has %d slot(s) to seed: %s", len(slots), {k.value: v for k, v in by_status.items()})
    if not apply:
        logger.info("Report only; re-run with --apply to write these to the database")
        return

    database.connect()
    await database.ensure_indexes()
    import_id = import_repository.new_import_id()
    created = upgraded = unchanged = 0
    for (_, phone, appointment_date, appointment_time), entry in slots.items():
        patient = await patient_repository.upsert(entry["patient"], phone, entry["phone_raw"])
        appointment = await appointment_repository.find_slot(patient["_id"], appointment_date, appointment_time)
        if appointment is None:
            appointment = await appointment_repository.create(patient["_id"], appointment_date, appointment_time, "", import_id)
            created += 1
        elif appointment["status"] not in UPGRADEABLE:
            unchanged += 1
            continue
        else:
            upgraded += 1
        fields = {"status": entry["status"].value, "status_reason": "Imported from legacy reminder log"}
        if entry["status"] is AppointmentStatus.SENT:
            fields["sent_at"] = parse_legacy_timestamp(entry["timestamp"], config.default_time_zone)
        await appointment_repository.update_fields(appointment["_id"], fields)

    await import_repository.save(import_id, {
        "file_name": f"{path.name} (legacy seed)",
        "dates": sorted({d.isoformat() for (_, _, d, _) in slots}),
        "counts": {"rows": len(slots), "created": created, "updated": upgraded, "reactivated": 0, "unchanged": unchanged, "cancelled": 0, "invalid": len(problems)},
        "rows": [],
        "cancelled": [],
    })
    logger.info("Seeded: %d created, %d upgraded, %d already final", created, upgraded, unchanged)
    await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path, default=BASE_DIR / "logs" / "reminder_log.csv")
    parser.add_argument("--apply", action="store_true", help="Write to the database (default: report only)")
    args = parser.parse_args()
    configure_logging(config.log_level)
    asyncio.run(seed(args.file, args.apply))


if __name__ == "__main__":
    main()
