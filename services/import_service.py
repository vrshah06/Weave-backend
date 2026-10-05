import logging
from collections import defaultdict
from datetime import date
from typing import cast

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from core.errors import InvalidRequestError, NotFoundError
from models.enums import CANCELLABLE_APPOINTMENT_STATUSES, AppointmentStatus, ImportRowStatus
from repositories import appointment_repository, import_repository, patient_repository
from utils.appointment_csv import AppointmentRow, CsvFormatError, decode_csv_bytes, parse_appointment_csv
from utils.object_ids import parse_path_id

logger = logging.getLogger(__name__)


async def _upsert_appointment(row: AppointmentRow, patient_id: ObjectId, import_id: ObjectId) -> tuple[dict, ImportRowStatus]:
    existing = await appointment_repository.find_slot(patient_id, row.appointment_date, row.appointment_time)
    if existing is None:
        try:
            created = await appointment_repository.create(patient_id, row.appointment_date, row.appointment_time, row.provider, import_id)
            return created, ImportRowStatus.CREATED
        except DuplicateKeyError:
            # Another import created the same slot concurrently, so it exists now.
            existing = cast(dict, await appointment_repository.find_slot(patient_id, row.appointment_date, row.appointment_time))

    if existing["status"] == AppointmentStatus.CANCELLED.value:
        await appointment_repository.update_fields(existing["_id"], {
            "status": AppointmentStatus.PENDING.value, "status_reason": None, "provider": row.provider, "import_id": import_id,
        })
        return existing, ImportRowStatus.REACTIVATED
    if existing.get("provider", "") != row.provider:
        await appointment_repository.update_fields(existing["_id"], {"provider": row.provider, "import_id": import_id})
        return existing, ImportRowStatus.UPDATED
    return existing, ImportRowStatus.UNCHANGED


async def import_appointments(file_name: str, content: bytes) -> dict:
    try:
        parsed = parse_appointment_csv(decode_csv_bytes(content))
    except CsvFormatError as exc:
        raise InvalidRequestError(str(exc))
    if not parsed.rows:
        raise InvalidRequestError("CSV contains no valid appointment rows", details=[
            {"row": e.row_number, "message": e.message} for e in parsed.errors[:50]
        ])

    import_id = import_repository.new_import_id()
    rows = [{"row": e.row_number, "status": ImportRowStatus.INVALID.value, "message": e.message} for e in parsed.errors]
    kept_ids_by_date: dict[date, list[ObjectId]] = defaultdict(list)
    seen_slots: set[tuple] = set()

    for row in parsed.rows:
        slot = (row.patient.name_key, row.phone, row.appointment_date, row.appointment_time)
        base = {
            "row": row.row_number,
            "patient_name": row.patient.full_name,
            "phone": row.phone,
            "appointment_date": row.appointment_date.isoformat(),
            "appointment_time": row.appointment_time,
        }
        if slot in seen_slots:
            rows.append({**base, "status": ImportRowStatus.DUPLICATE_IN_FILE.value, "message": "Same patient and time slot appears earlier in this file"})
            continue
        seen_slots.add(slot)

        patient = await patient_repository.upsert(row.patient, row.phone, row.phone_raw)
        appointment, status = await _upsert_appointment(row, patient["_id"], import_id)
        kept_ids_by_date[row.appointment_date].append(appointment["_id"])
        rows.append({**base, "status": status.value, "appointment_id": str(appointment["_id"])})

    cancelled = []
    for appointment_date, kept_ids in kept_ids_by_date.items():
        for appointment in await appointment_repository.cancel_missing_from_import(
            appointment_date, kept_ids, CANCELLABLE_APPOINTMENT_STATUSES, import_id
        ):
            cancelled.append({
                "appointment_id": str(appointment["_id"]),
                "patient_name": appointment["patient"]["full_name"],
                "appointment_date": appointment["appointment_date"],
                "appointment_time": appointment["appointment_time"],
            })

    rows.sort(key=lambda r: r["row"])
    status_counts = defaultdict(int)
    for r in rows:
        status_counts[r["status"]] += 1
    document = await import_repository.save(import_id, {
        "file_name": file_name,
        "dates": sorted(d.isoformat() for d in kept_ids_by_date),
        "counts": {
            "rows": parsed.row_count,
            "created": status_counts[ImportRowStatus.CREATED.value],
            "updated": status_counts[ImportRowStatus.UPDATED.value],
            "reactivated": status_counts[ImportRowStatus.REACTIVATED.value],
            "unchanged": status_counts[ImportRowStatus.UNCHANGED.value],
            "cancelled": len(cancelled),
            "invalid": status_counts[ImportRowStatus.INVALID.value] + status_counts[ImportRowStatus.DUPLICATE_IN_FILE.value],
        },
        "rows": rows,
        "cancelled": cancelled,
    })
    logger.info("Import %s (%s): %s", import_id, file_name, document["counts"])
    return document


async def list_page(limit: int, offset: int) -> tuple[list[dict], int]:
    return await import_repository.list_page(limit, offset)


async def get(import_id: str) -> dict:
    document = await import_repository.find_by_id(parse_path_id(import_id, "Import"))
    if not document:
        raise NotFoundError("Import not found")
    return document
