from datetime import datetime

from repositories import appointment_repository, patient_repository
from utils.csv_parser import parse_appointment_csv
from automation.logging_utils import setup_logger

logger = setup_logger("weave_api")


def _row_result(row: dict, appointment_id) -> dict:
    return {
        "rowIndex": row["rowIndex"],
        "appointmentId": str(appointment_id),
        "patientName": row["fullName"],
        "phone": row["phone"],
        "appointmentDate": row["appointmentDateIso"],
        "appointmentTime": row["appointmentTime"],
        "provider": row["provider"]
    }


async def import_appointments_csv(csv_content: str) -> dict:
    parsed = parse_appointment_csv(csv_content)

    imported = []
    duplicates = []
    errors = list(parsed["errors"])

    for row in parsed["rows"]:
        try:
            patient = await patient_repository.find_by_name_and_phone(row["fullName"], row["phone"])
            if not patient:
                patient = await patient_repository.create({
                    "firstName": row["firstName"],
                    "lastName": row["lastName"],
                    "fullName": row["fullName"],
                    "phone": row["phone"]
                })

            appt_filter = {
                "patientId": patient["_id"],
                "appointmentDate": row["appointmentDateIso"],
                "appointmentTime": row["appointmentTime"]
            }

            existing = await appointment_repository.find_one(appt_filter)
            if existing:
                duplicates.append(_row_result(row, existing["_id"]))
            else:
                res = await appointment_repository.create({
                    **appt_filter,
                    "provider": row["provider"],
                    "reminderSelected": True,
                    "reminderStatus": "PENDING",
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                })
                imported.append(_row_result(row, res.inserted_id))
        except Exception:
            logger.exception("Failed to import CSV row %s", row["rowIndex"])
            errors.append(f"Row {row['rowIndex']} skipped: could not be saved")

    return {
        "summary": {
            "rowsReceived": parsed["totalReceived"],
            "imported": len(imported),
            "duplicates": len(duplicates),
            "invalid": len(errors)
        },
        "imported": imported,
        "duplicates": duplicates,
        "errors": errors
    }
