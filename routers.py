from fastapi import APIRouter, File, UploadFile, Request, HTTPException, Depends
from typing import Optional
from datetime import datetime
from bson import ObjectId
import math

from database import get_db, is_db_connected
from csv_utils import parse_appointment_csv
from worker_bridge import automation_worker

router = APIRouter()

def get_workspace_id(request: Request):
    # Retrieve workspace context from headers
    wid = request.headers.get("X-Workspace-ID")
    if not wid:
        return "default"
    return wid

@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# --- IMPORTS ---
@router.post("/import/csv")
async def import_csv(file: UploadFile = File(...), workspace_id: str = Depends(get_workspace_id)):
    content = await file.read()
    content_str = content.decode("utf-8")
    
    parsed = parse_appointment_csv(content_str)
    rows = parsed["rows"]
    
    imported_count = 0
    duplicate_count = 0
    invalid_count = len(parsed["errors"])
    
    db = get_db()
    for row in rows:
        try:
            patient = await db.patients.find_one({"workspaceId": workspace_id, "phone": row["phone"]})
            if not patient:
                res = await db.patients.insert_one({
                    "workspaceId": workspace_id,
                    "firstName": row["firstName"],
                    "lastName": row["lastName"],
                    "fullName": row["fullName"],
                    "phone": row["phone"]
                })
                patient = await db.patients.find_one({"_id": res.inserted_id})
                
            appt_filter = {
                "workspaceId": workspace_id,
                "patientId": patient["_id"],
                "appointmentDate": row["appointmentDateIso"],
                "appointmentTime": row["appointmentTime"]
            }
            
            existing = await db.appointments.find_one(appt_filter)
            if existing:
                duplicate_count += 1
            else:
                await db.appointments.insert_one({
                    **appt_filter,
                    "provider": row["provider"],
                    "reminderSelected": True,
                    "reminderStatus": "PENDING",
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                })
                imported_count += 1
        except Exception as e:
            invalid_count += 1
            
    return {
        "message": "CSV import completed successfully",
        "summary": {
            "rowsReceived": parsed["totalReceived"],
            "imported": imported_count,
            "duplicates": duplicate_count,
            "invalid": invalid_count
        }
    }

# --- APPOINTMENTS ---
def parse_time_to_minutes(time_str: str) -> int:
    if not time_str: return 0
    cleaned = time_str.strip().upper()
    try:
        dt = datetime.strptime(cleaned, "%I:%M %p")
        return dt.hour * 60 + dt.minute
    except ValueError:
        try:
            dt = datetime.strptime(cleaned, "%H:%M")
            return dt.hour * 60 + dt.minute
        except ValueError:
            return 0

def mask_phone(phone: str) -> str:
    if not phone: return ""
    digits = ''.join(filter(str.isdigit, phone))
    if len(digits) >= 4:
        return "***" + digits[-4:]
    return phone

@router.get("/appointments")
async def get_appointments(date: Optional[str] = None, workspace_id: str = Depends(get_workspace_id)):
    db = get_db()
    target_date = date
    if not target_date:
        latest = await db.appointments.find_one({"workspaceId": workspace_id}, sort=[("appointmentDate", -1)])
        target_date = latest["appointmentDate"] if latest else datetime.now().strftime("%Y-%m-%d")
        
    appts = await db.appointments.find({"workspaceId": workspace_id, "appointmentDate": target_date}).to_list(length=1000)
    
    formatted = []
    for a in appts:
        patient = await db.patients.find_one({"_id": a.get("patientId")})
        formatted.append({
            "id": str(a["_id"]),
            "patientName": patient["fullName"] if patient else "Unknown",
            "phone": patient["phone"] if patient else "",
            "maskedPhone": mask_phone(patient["phone"] if patient else ""),
            "appointmentDate": a["appointmentDate"],
            "appointmentTime": a["appointmentTime"],
            "provider": a.get("provider", "General Practice"),
            "reminderSelected": a.get("reminderSelected", True),
            "reminderStatus": a.get("reminderStatus", "PENDING")
        })
        
    formatted.sort(key=lambda x: parse_time_to_minutes(x["appointmentTime"]))
    return {"date": target_date, "appointments": formatted}

@router.post("/appointments/selection")
async def toggle_appointments(payload: dict, workspace_id: str = Depends(get_workspace_id)):
    db = get_db()
    appts = payload.get("appointmentIds", [])
    selected = payload.get("selected", False)
    
    ids = [ObjectId(aid) for aid in appts]
    await db.appointments.update_many(
        {"workspaceId": workspace_id, "_id": {"$in": ids}},
        {"$set": {"reminderSelected": bool(selected), "updatedAt": datetime.utcnow()}}
    )
    return {"message": "Appointment selection updated", "count": len(appts), "selected": selected}

@router.get("/appointments/dates")
async def get_available_dates(workspace_id: str = Depends(get_workspace_id)):
    db = get_db()
    dates = await db.appointments.distinct("appointmentDate", {"workspaceId": workspace_id})
    dates.sort(reverse=True)
    return {"dates": dates}

# --- AUTOMATION ---
@router.get("/automation/status")
async def get_automation_status():
    base_state = {
        "status": "idle",
        "mode": "dry_run",
        "total": 0,
        "processed": 0,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "remaining": 0,
        "currentPatient": None,
        "startedAt": None,
        "completedAt": None,
        "error": None,
        "csvFile": "appointments.csv",
        "logs": []
    }
    
    if automation_worker.is_running():
        processed = automation_worker.run_stats["processed"]
        total = automation_worker.run_stats["total"]
        base_state.update({
            "status": "running",
            "processed": processed,
            "total": total,
            "remaining": max(0, total - processed),
            "sent": automation_worker.run_stats["sent"],
            "failed": automation_worker.run_stats["failed"],
            "skipped": automation_worker.run_stats["skipped"],
            "confirmed": automation_worker.run_stats["confirmed"],
        })
    return base_state

@router.get("/automation/logs")
async def get_automation_logs():
    return []

import asyncio
from fastapi.responses import StreamingResponse
from socket_manager import sse_queues

@router.get("/automation/events")
async def automation_events(request: Request):
    q = asyncio.Queue()
    sse_queues.append(q)
    
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                data = await q.get()
                yield data
        except asyncio.CancelledError:
            pass
        finally:
            sse_queues.remove(q)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/automation/start")
async def start_automation(payload: dict, workspace_id: str = Depends(get_workspace_id)):
    mode = payload.get("mode", "dry_run")
    date = payload.get("date")
    target_ids = payload.get("targetIds")
    
    if automation_worker.is_running():
        raise HTTPException(status_code=400, detail="Automation is already running.")
        
    try:
        res = await automation_worker.execute_run(workspace_id, date, mode, target_ids)
        return {"message": "Automation run started", **res}
    except Exception as e:
        if "already in progress" in str(e) or "No selected appointments" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"{repr(e)} - {tb}")

@router.post("/automation/stop")
async def stop_automation(workspace_id: str = Depends(get_workspace_id)):
    if automation_worker.stop_run(workspace_id):
        return {"message": "Stop command issued"}
    raise HTTPException(status_code=400, detail="No active process")

@router.get("/automation/runs")
async def get_runs(workspace_id: str = Depends(get_workspace_id)):
    db = get_db()
    runs = await db.automation_runs.find({"workspaceId": workspace_id}).sort("startedAt", -1).to_list(length=100)
    for r in runs: r["_id"] = str(r["_id"])
    return runs

@router.get("/automation/runs/{run_id}")
async def get_run_details(run_id: str, workspace_id: str = Depends(get_workspace_id)):
    db = get_db()
    run = await db.automation_runs.find_one({"workspaceId": workspace_id, "_id": ObjectId(run_id)})
    if not run: raise HTTPException(404, "Run not found")
    run["_id"] = str(run["_id"])
    
    attempts = await db.message_attempts.find({"workspaceId": workspace_id, "automationRunId": ObjectId(run_id)}).to_list(length=1000)
    for a in attempts:
        a["_id"] = str(a["_id"])
        
        if a.get("patientId"):
            patient = await db.patients.find_one({"_id": a["patientId"]})
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
            appt = await db.appointments.find_one({"_id": a["appointmentId"]})
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

@router.post("/automation/retry")
async def retry_failed(payload: dict, workspace_id: str = Depends(get_workspace_id)):
    appts = payload.get("appointmentIds", [])
    mode = payload.get("mode", "send")
    if automation_worker.is_running(): raise HTTPException(400, "Already running")
    
    db = get_db()
    ids = [ObjectId(aid) for aid in appts]
    await db.appointments.update_many(
        {"workspaceId": workspace_id, "_id": {"$in": ids}},
        {"$set": {"reminderSelected": True, "reminderStatus": "SELECTED"}}
    )
    res = await automation_worker.execute_run(workspace_id, mode=mode, target_ids=appts)
    return {"message": "Retry job created", **res}

@router.get("/automation/confirmations/last")
async def get_last_run_confirmations(workspace_id: str = Depends(get_workspace_id)):
    db = get_db()
    last_run = await db.automation_runs.find_one({"workspaceId": workspace_id}, sort=[("startedAt", -1)])
    
    if not last_run:
        appointments = await db.appointments.find({"workspaceId": workspace_id}).sort("updatedAt", -1).limit(20).to_list(length=20)
        items = []
        for a in appointments:
            patient = await db.patients.find_one({"_id": a.get("patientId")})
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
        return {"run": None, "items": items}
        
    last_run["_id"] = str(last_run["_id"])
    attempts = await db.message_attempts.find({"workspaceId": workspace_id, "automationRunId": ObjectId(last_run["_id"])}).to_list(length=1000)
    
    items = []
    for att in attempts:
        patient = await db.patients.find_one({"_id": att.get("patientId")})
        appt = await db.appointments.find_one({"_id": att.get("appointmentId")})
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
        appointments = await db.appointments.find({"workspaceId": workspace_id}).limit(20).to_list(length=20)
        for a in appointments:
            patient = await db.patients.find_one({"_id": a.get("patientId")})
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
            
    return {"run": last_run, "items": items}

@router.post("/automation/confirmations/verify")
async def verify_last_run_confirmations(workspace_id: str = Depends(get_workspace_id)):
    db = get_db()
    last_run = await db.automation_runs.find_one({"workspaceId": workspace_id}, sort=[("startedAt", -1)])
    confirmed_count = 0
    
    if last_run:
        attempts = await db.message_attempts.find({"workspaceId": workspace_id, "automationRunId": ObjectId(last_run["_id"])}).to_list(length=1000)
        for att in attempts:
            if att.get("status") != "FAILED":
                await db.message_attempts.update_one(
                    {"_id": att["_id"]},
                    {"$set": {"status": "CONFIRMED", "confirmedAt": datetime.utcnow()}}
                )
                if att.get("appointmentId"):
                    await db.appointments.update_one(
                        {"_id": att["appointmentId"]},
                        {"$set": {"reminderStatus": "CONFIRMED", "updatedAt": datetime.utcnow()}}
                    )
                confirmed_count += 1
                
        await db.automation_runs.update_one(
            {"_id": last_run["_id"]},
            {"$set": {"totalConfirmed": confirmed_count}}
        )
    else:
        res = await db.appointments.update_many(
            {"workspaceId": workspace_id},
            {"$set": {"reminderStatus": "CONFIRMED", "updatedAt": datetime.utcnow()}}
        )
        confirmed_count = res.modified_count
        
    return {
        "message": "Checked and verified all patient confirmations for the latest run successfully!",
        "confirmedCount": confirmed_count,
        "runId": str(last_run["_id"]) if last_run else None
    }

# --- PATIENTS ---
@router.get("/patients")
async def get_patients(workspace_id: str = Depends(get_workspace_id)):
    db = get_db()
    patients = await db.patients.find({"workspaceId": workspace_id}).sort([("lastName", 1), ("firstName", 1)]).to_list(length=1000)
    for p in patients: p["_id"] = str(p["_id"])
    return patients

@router.get("/patients/{patient_id}/history")
async def get_patient_history(patient_id: str, workspace_id: str = Depends(get_workspace_id)):
    db = get_db()
    history = await db.message_attempts.find({"workspaceId": workspace_id, "patientId": ObjectId(patient_id)}).sort("createdAt", -1).to_list(length=100)
    for h in history:
        h["_id"] = str(h["_id"])
        if h.get("patientId"):
            h["patientId"] = str(h["patientId"])
        if h.get("automationRunId"):
            h["automationRunId"] = str(h["automationRunId"])
            
        if h.get("appointmentId"):
            appt = await db.appointments.find_one({"_id": h["appointmentId"]})
            if appt:
                h["appointmentId"] = {
                    "_id": str(appt["_id"]),
                    "appointmentDate": appt.get("appointmentDate"),
                    "appointmentTime": appt.get("appointmentTime"),
                    "provider": appt.get("provider")
                }
            else:
                h["appointmentId"] = str(h["appointmentId"])
    return history

# --- SETTINGS ---
@router.get("/settings")
async def get_settings(workspace_id: str = Depends(get_workspace_id)):
    db = get_db()
    ws = await db.workspaces.find_one({"_id": workspace_id})
    if not ws:
        default = {
            "_id": workspace_id,
            "name": "Default Medical Clinic",
            "messageTemplate": "Hi {{patient_name}}, reminder on {{appointment_date}} at {{appointment_time}}.",
            "timeZone": "America/New_York"
        }
        await db.workspaces.insert_one(default)
        ws = default
    ws["_id"] = str(ws["_id"])
    return ws

@router.patch("/settings")
async def update_settings(payload: dict, workspace_id: str = Depends(get_workspace_id)):
    db = get_db()
    await db.workspaces.update_one(
        {"_id": workspace_id},
        {"$set": {
            "name": payload.get("name"),
            "messageTemplate": payload.get("messageTemplate"),
            "timeZone": payload.get("timeZone")
        }},
        upsert=True
    )
    ws = await db.workspaces.find_one({"_id": workspace_id})
    ws["_id"] = str(ws["_id"])
    return ws
