from datetime import date
from typing import Optional

from models.appointment_models import AppointmentResponse
from models.import_models import ImportResponse, ImportSummaryResponse
from models.patient_models import PatientResponse
from models.run_models import RunCounts, RunItemResponse, RunLogResponse, RunResponse


def present_patient(patient: dict) -> PatientResponse:
    return PatientResponse(
        id=str(patient["_id"]),
        full_name=patient["full_name"],
        first_name=patient["first_name"],
        last_name=patient["last_name"],
        phone=patient["phone"],
        created_at=patient["created_at"],
    )


def present_appointment(appointment: dict) -> AppointmentResponse:
    patient = appointment["patient"]
    return AppointmentResponse(
        id=str(appointment["_id"]),
        patient_id=str(patient["_id"]),
        patient_name=patient["full_name"],
        phone=patient["phone"],
        appointment_date=date.fromisoformat(appointment["appointment_date"]),
        appointment_time=appointment["appointment_time"],
        provider=appointment.get("provider", ""),
        status=appointment["status"],
        status_reason=appointment.get("status_reason"),
        excluded=appointment.get("excluded", False),
        sent_at=appointment.get("sent_at"),
        updated_at=appointment["updated_at"],
    )


def _import_fields(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "file_name": document["file_name"],
        "dates": document["dates"],
        "counts": document["counts"],
        "created_at": document["created_at"],
    }


def present_import(document: dict) -> ImportResponse:
    return ImportResponse(**_import_fields(document), rows=document["rows"], cancelled=document["cancelled"])


def present_import_summary(document: dict) -> ImportSummaryResponse:
    return ImportSummaryResponse(**_import_fields(document))


def present_run(run: dict) -> RunResponse:
    counts = run["counts"]
    return RunResponse(
        id=str(run["_id"]),
        appointment_date=date.fromisoformat(run["appointment_date"]),
        mode=run["mode"],
        status=run["status"],
        stop_requested=run.get("stop_requested", False),
        counts=RunCounts(**counts, remaining=max(0, counts["total"] - counts["processed"])),
        error=run.get("error"),
        queued_at=run["queued_at"],
        started_at=run.get("started_at"),
        finished_at=run.get("finished_at"),
        heartbeat_at=run.get("heartbeat_at"),
    )


def screenshot_url(run_id: str, screenshot_id: Optional[object]) -> Optional[str]:
    return f"/api/v1/runs/{run_id}/screenshots/{screenshot_id}" if screenshot_id else None


def present_run_item(item: dict) -> RunItemResponse:
    run_id = str(item["run_id"])
    return RunItemResponse(
        id=str(item["_id"]),
        run_id=run_id,
        appointment_id=str(item["appointment_id"]),
        patient_name=item["patient"]["full_name"],
        appointment_time=item["appointment"]["appointment_time"],
        status=item["status"],
        reason=item.get("reason"),
        screenshot_url=screenshot_url(run_id, item.get("screenshot_id")),
        started_at=item["started_at"],
        finished_at=item.get("finished_at"),
    )


def present_run_log(log: dict) -> RunLogResponse:
    return RunLogResponse(
        id=str(log["_id"]),
        run_id=str(log["run_id"]),
        appointment_id=str(log["appointment_id"]) if log.get("appointment_id") else None,
        level=log["level"],
        event=log["event"],
        message=log["message"],
        created_at=log["created_at"],
    )
