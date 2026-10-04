from datetime import datetime
from typing import Optional

from bson import ObjectId

from core.exceptions import AutomationAlreadyRunningError, NotFoundError
from repositories import appointment_repository, automation_run_repository, message_attempt_repository, patient_repository
from services.automation_runner import automation_runner


async def get_status() -> dict:
    run = await automation_run_repository.find_latest()
    if not run:
        raise NotFoundError("No runs found")

    run_id = str(run["_id"])
    status = {
        "runId": run_id,
        "status": run.get("status", "").lower(),
        "mode": run.get("mode"),
        "date": run.get("appointmentDate"),
        "total": run.get("totalSelected", 0),
        "processed": run.get("totalProcessed", 0),
        "sent": run.get("totalSent", 0),
        "confirmed": run.get("totalConfirmed", 0),
        "failed": run.get("totalFailed", 0),
        "skipped": run.get("totalSkipped", 0),
        "startedAt": run.get("startedAt"),
        "completedAt": run.get("completedAt"),
    }

    if automation_runner.is_running() and automation_runner.current_run_id == run_id:
        stats = automation_runner.run_stats
        status.update({
            "status": "running",
            "processed": stats["processed"],
            "sent": stats["sent"],
            "confirmed": stats["confirmed"],
            "failed": stats["failed"],
            "skipped": stats["skipped"],
        })
    elif run.get("status") == "STARTING":
        # The process is gone but the run was never finalised (e.g. the server restarted mid-run).
        status["status"] = "interrupted"

    status["remaining"] = max(0, status["total"] - status["processed"])
    return status


async def start_run(mode: str, date: Optional[str], target_ids: Optional[list]) -> dict:
    if automation_runner.is_running():
        raise AutomationAlreadyRunningError("Automation is already running.")
    return await automation_runner.execute_run(date, mode, target_ids)


def stop_run() -> None:
    automation_runner.stop_run()


async def retry_appointments(appointment_ids: list, mode: str) -> dict:
    if automation_runner.is_running():
        raise AutomationAlreadyRunningError("Already running")
    ids = [ObjectId(aid) for aid in appointment_ids]
    await appointment_repository.update_many(ids, {"reminderSelected": True, "reminderStatus": "SELECTED"})
    return await automation_runner.execute_run(mode=mode, target_ids=appointment_ids)


async def list_runs() -> list:
    runs = await automation_run_repository.list_all()
    for r in runs: r["_id"] = str(r["_id"])
    return runs


async def get_run_details(run_id: str) -> dict:
    run = await automation_run_repository.find_by_id(run_id)
    if not run:
        raise NotFoundError("Run not found")
    run["_id"] = str(run["_id"])

    attempts = await message_attempt_repository.list_by_run(run_id)
    for a in attempts:
        a["_id"] = str(a["_id"])

        if a.get("patientId"):
            patient = await patient_repository.find_by_id(a["patientId"])
            if patient:
                a["patientId"] = {
                    "_id": str(patient["_id"]),
                    "firstName": patient.get("firstName"),
                    "lastName": patient.get("lastName"),
                    "fullName": patient.get("fullName"),
                    "phone": patient.get("phone")
                }
            else:
                a["patientId"] = str(a["patientId"])

        if a.get("appointmentId"):
            appt = await appointment_repository.find_by_id(a["appointmentId"])
            if appt:
                a["appointmentId"] = {
                    "_id": str(appt["_id"]),
                    "appointmentDate": appt.get("appointmentDate"),
                    "appointmentTime": appt.get("appointmentTime")
                }
            else:
                a["appointmentId"] = str(a["appointmentId"])

        if a.get("automationRunId"):
            a["automationRunId"] = str(a["automationRunId"])

    return {"run": run, "attempts": attempts}


async def _appointment_confirmation_items(appointments: list) -> list:
    items = []
    for a in appointments:
        patient = await patient_repository.find_by_id(a.get("patientId"))
        items.append({
            "_id": str(a["_id"]),
            "appointmentId": str(a["_id"]),
            "patientName": patient["fullName"] if patient else "Patient",
            "phone": patient["phone"] if patient else "",
            "appointmentDate": a.get("appointmentDate", ""),
            "appointmentTime": a.get("appointmentTime", ""),
            "status": "SENT" if a.get("reminderStatus") == "PENDING" else a.get("reminderStatus"),
            "sentAt": a.get("updatedAt", a.get("createdAt")),
            "confirmedAt": a.get("updatedAt") if a.get("reminderStatus") == "CONFIRMED" else None
        })
    return items


async def get_last_run_confirmations() -> dict:
    last_run = await automation_run_repository.find_latest()

    if not last_run:
        appointments = await appointment_repository.list_recent(sort_by_updated=True)
        return {"run": None, "items": await _appointment_confirmation_items(appointments)}

    last_run["_id"] = str(last_run["_id"])
    attempts = await message_attempt_repository.list_by_run(last_run["_id"])

    items = []
    for att in attempts:
        patient = await patient_repository.find_by_id(att.get("patientId"))
        appt = await appointment_repository.find_by_id(att.get("appointmentId"))
        items.append({
            "_id": str(att["_id"]),
            "attemptId": str(att["_id"]),
            "appointmentId": str(appt["_id"]) if appt else None,
            "patientName": patient["fullName"] if patient else "Patient",
            "phone": patient["phone"] if patient else "",
            "appointmentDate": appt.get("appointmentDate", "") if appt else "",
            "appointmentTime": appt.get("appointmentTime", "") if appt else "",
            "status": att.get("status"),
            "message": att.get("message"),
            "sentAt": att.get("sentAt", att.get("createdAt")),
            "confirmedAt": att.get("confirmedAt")
        })

    if not items:
        appointments = await appointment_repository.list_recent()
        items = await _appointment_confirmation_items(appointments)

    return {"run": last_run, "items": items}


async def verify_last_run_confirmations() -> dict:
    last_run = await automation_run_repository.find_latest()
    confirmed_count = 0

    if last_run:
        attempts = await message_attempt_repository.list_by_run(last_run["_id"])
        for att in attempts:
            if att.get("status") != "FAILED":
                await message_attempt_repository.mark_confirmed(att["_id"])
                if att.get("appointmentId"):
                    await appointment_repository.update_status(att["appointmentId"], "CONFIRMED")
                confirmed_count += 1

        await automation_run_repository.update(last_run["_id"], {"totalConfirmed": confirmed_count})
    else:
        res = await appointment_repository.update_all({"reminderStatus": "CONFIRMED", "updatedAt": datetime.utcnow()})
        confirmed_count = res.modified_count

    return {
        "confirmedCount": confirmed_count,
        "runId": str(last_run["_id"]) if last_run else None
    }
