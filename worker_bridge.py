import asyncio
import os
import json
import sys
import tempfile
import traceback
from datetime import datetime
from bson import ObjectId

from database import get_db, is_db_connected
from socket_manager import emit_workspace_event

class AutomationWorkerBridge:
    def __init__(self):
        self.active_process = None
        self.current_run_id = None
        self.run_stats = {
            "processed": 0,
            "sent": 0,
            "confirmed": 0,
            "failed": 0,
            "skipped": 0,
            "total": 0
        }
        self.items = []
        
    def is_running(self):
        return self.active_process is not None

    async def export_database_to_payload(self, workspace_id, appointment_date, target_ids=None):
        db = get_db()
        query = {"workspaceId": workspace_id}
        
        if not appointment_date and not target_ids:
            appointment_date = datetime.now().strftime("%Y-%m-%d")
            
        if appointment_date:
            query["appointmentDate"] = appointment_date
            
        if target_ids:
            query["_id"] = {"$in": [ObjectId(tid) if isinstance(tid, str) and len(tid) == 24 else tid for tid in target_ids]}
            
        appointments = await db.appointments.find(query).to_list(length=1000)
        
        valid_items = []
        for appt in appointments:
            if appt.get("reminderStatus") in ["CONFIRMED", "SENT", "SKIPPED"] and not target_ids:
                continue
                
            if not appt.get("reminderSelected", True) and not target_ids:
                continue
                
            patient = await db.patients.find_one({"_id": appt.get("patientId")})
            if not patient:
                continue
                
            valid_items.append({
                "appointmentId": str(appt["_id"]),
                "patientId": str(patient["_id"]),
                "patient_name": patient.get("fullName", ""),
                "phone": patient.get("phone", ""),
                "appointment_date": appt.get("appointmentDate", ""),
                "appointment_time": appt.get("appointmentTime", ""),
                "provider": appt.get("provider", "")
            })
            
        if not valid_items:
            return None, 0, []
            
        temp_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(temp_dir, exist_ok=True)
        csv_path = os.path.join(temp_dir, f"temp_run_{int(datetime.now().timestamp()*1000)}.csv")
        
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("patient_name,phone,appointment_date,appointment_time,provider\n")
            for item in valid_items:
                f.write(f'"{item["patient_name"]}","{item["phone"]}","{item["appointment_date"]}","{item["appointment_time"]}","{item["provider"]}"\n')
                
        return csv_path, len(valid_items), valid_items

    async def execute_run(self, workspace_id, appointment_date=None, mode="dry_run", target_ids=None):
        if self.active_process:
            raise Exception("An automation run is already in progress.")
            
        db = get_db()
        csv_path, count, self.items = await self.export_database_to_payload(workspace_id, appointment_date, target_ids)
        
        if count == 0:
            raise Exception("No selected appointments found for the specified date.")
            
        self.run_stats = {
            "processed": 0, "sent": 0, "confirmed": 0,
            "failed": 0, "skipped": 0, "total": count
        }
        
        run_record = {
            "workspaceId": workspace_id,
            "appointmentDate": appointment_date or datetime.now().strftime("%Y-%m-%d"),
            "mode": mode,
            "status": "STARTING",
            "totalSelected": count,
            "startedAt": datetime.utcnow()
        }
        
        res = await db.automation_runs.insert_one(run_record)
        self.current_run_id = str(res.inserted_id)
        
        await emit_workspace_event(workspace_id, "state_update", {
            "state": {
                "status": "starting",
                "mode": mode,
                "total": count,
                "remaining": count,
                "startedAt": datetime.utcnow().isoformat()
            }
        })
        
        await emit_workspace_event(workspace_id, "automation:started", {
            "runId": self.current_run_id,
            "mode": mode,
            "total": count,
            "date": appointment_date
        })
        
        is_send_mode = (mode == "send")
        mode_flag = "--send" if is_send_mode else "--dry-run"
        
        root_dir = os.path.dirname(__file__)
        python_cmd = sys.executable
        args = ["main.py", mode_flag, "--file", csv_path]
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        import subprocess
        import threading
        
        self.active_process = subprocess.Popen(
            [python_cmd, *args],
            cwd=root_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        loop = asyncio.get_running_loop()
        
        def pump_stream(stream, is_stderr):
            for line in stream:
                line = line.strip()
                if not line: continue
                asyncio.run_coroutine_threadsafe(self._process_line(line, workspace_id, self.current_run_id, is_stderr), loop)
                
        def wait_process():
            code = self.active_process.wait()
            asyncio.run_coroutine_threadsafe(self._finalize_run(code, csv_path, workspace_id), loop)

        threading.Thread(target=pump_stream, args=(self.active_process.stdout, False), daemon=True).start()
        threading.Thread(target=pump_stream, args=(self.active_process.stderr, True), daemon=True).start()
        threading.Thread(target=wait_process, daemon=True).start()
        
        return {"runId": self.current_run_id, "count": count, "mode": mode}
        
    async def _process_line(self, decoded, workspace_id, run_id, is_stderr):
        try:
            if decoded.startswith("{") and decoded.endswith("}") and '"type":' in decoded:
                event = json.loads(decoded)
                await self._process_event(event, workspace_id, run_id)
            else:
                await emit_workspace_event(workspace_id, "log", {
                    "log": {
                        "patient": "System",
                        "action": "Console Log",
                        "status": "running" if not is_stderr else "failed",
                        "message": decoded,
                        "time": datetime.utcnow().isoformat()
                    }
                })
        except Exception:
            pass

    async def _read_stream(self, stream, workspace_id, run_id, is_stderr):
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode('utf-8').strip()
            if not text:
                continue
                
            if "[EVENT]" in text:
                try:
                    json_str = text.split("[EVENT]")[1].strip()
                    event = json.loads(json_str)
                    await self._process_event(event, workspace_id, run_id)
                except Exception as e:
                    print(f"Error parsing event: {e}")
            elif is_stderr or "Error:" in text or "Exception:" in text or text.startswith("Traceback"):
                print(f"[Worker Error] {text}")

    async def _process_event(self, event, workspace_id, run_id):
        db = get_db()
        event_type = event.get("type")
        
        async def send_state():
            await emit_workspace_event(workspace_id, "state_update", {
                "state": {
                    "processed": self.run_stats["processed"],
                    "sent": self.run_stats["sent"],
                    "confirmed": self.run_stats["confirmed"],
                    "failed": self.run_stats["failed"],
                    "skipped": self.run_stats["skipped"],
                    "remaining": max(0, self.run_stats["total"] - self.run_stats["processed"])
                }
            })
            
        async def send_log(patient, action, status, message):
            await emit_workspace_event(workspace_id, "log", {
                "log": {
                    "patient": patient,
                    "action": action,
                    "status": status,
                    "message": message,
                    "time": datetime.utcnow().isoformat()
                }
            })
        
        if event_type == "PATIENT_START":
            await emit_workspace_event(workspace_id, "automation:patient", {
                "runId": run_id,
                "patientName": event.get("patient_name"),
                "phone": event.get("phone"),
                "position": event.get("position")
            })
            await emit_workspace_event(workspace_id, "state_update", {
                "state": {
                    "status": "running",
                    "currentPatient": {"name": event.get("patient_name"), "phone": event.get("phone")}
                }
            })
            await send_log(event.get("patient_name"), "Processing Patient", "running", f"Navigating to patient chat ({event.get('phone')})")
            
        elif event_type in ("MESSAGE_SENT", "MESSAGE_DRY_RUN"):
            is_sent = (event_type == "MESSAGE_SENT")
            self.run_stats["processed"] += 1
            if is_sent:
                self.run_stats["sent"] += 1
            else:
                self.run_stats["confirmed"] += 1
                
            await send_state()
            action_str = "Message Sent" if is_sent else "Dry Run Verified"
            status_str = "sent" if is_sent else "dry_run"
            msg_str = f"Successfully dispatched appointment reminder SMS to {event.get('phone')}" if is_sent else f"Dry Run: Verified chat window and reminder text for {event.get('patient_name')}"
            await send_log(event.get("patient_name"), action_str, status_str, msg_str)
                
            matched = next((i for i in self.items if i["phone"] == event.get("phone") or i["patient_name"] == event.get("patient_name")), None)
            
            if matched:
                try:
                    await db.appointments.update_one(
                        {"_id": ObjectId(matched["appointmentId"])},
                        {"$set": {"reminderStatus": "SENT" if is_sent else "CONFIRMED", "updatedAt": datetime.utcnow()}}
                    )
                    
                    attempt_count = await db.message_attempts.count_documents({"appointmentId": ObjectId(matched["appointmentId"])})
                    await db.message_attempts.insert_one({
                        "workspaceId": workspace_id,
                        "patientId": ObjectId(matched["patientId"]),
                        "appointmentId": ObjectId(matched["appointmentId"]),
                        "automationRunId": ObjectId(run_id),
                        "attemptNumber": attempt_count + 1,
                        "message": f"Appointment reminder for {matched['appointment_date']} at {matched['appointment_time']}",
                        "status": "SENT" if is_sent else "CONFIRMED",
                        "sentAt": datetime.utcnow(),
                        "confirmedAt": None if is_sent else datetime.utcnow()
                    })
                except Exception as e:
                    print(f"DB Update error: {e}")
                    
            await emit_workspace_event(workspace_id, "automation:sent", {
                "runId": run_id,
                "patientName": event.get("patient_name"),
                "phone": event.get("phone"),
                "isDryRun": not is_sent
            })
            
        elif event_type == "PATIENT_FAILED":
            self.run_stats["processed"] += 1
            self.run_stats["failed"] += 1
            
            await send_state()
            await send_log(event.get("patient_name", "Unknown"), "Message Failed / Not Delivered", "failed", event.get("reason", "Message not delivered or failed"))
            
            matched = next((i for i in self.items if i["phone"] == event.get("phone") or i["patient_name"] == event.get("patient_name")), None)
            
            if matched:
                try:
                    await db.appointments.update_one(
                        {"_id": ObjectId(matched["appointmentId"])},
                        {"$set": {"reminderStatus": "FAILED", "updatedAt": datetime.utcnow()}}
                    )
                    attempt_count = await db.message_attempts.count_documents({"appointmentId": ObjectId(matched["appointmentId"])})
                    await db.message_attempts.insert_one({
                        "workspaceId": workspace_id,
                        "patientId": ObjectId(matched["patientId"]),
                        "appointmentId": ObjectId(matched["appointmentId"]),
                        "automationRunId": ObjectId(run_id),
                        "attemptNumber": attempt_count + 1,
                        "status": "FAILED",
                        "failureReason": event.get("reason", "Not Delivered"),
                        "failedAt": datetime.utcnow()
                    })
                except Exception:
                    pass
                    
            await emit_workspace_event(workspace_id, "automation:failed", {
                "runId": run_id,
                "patientName": event.get("patient_name"),
                "reason": event.get("reason")
            })
            
        elif event_type == "PATIENT_SKIPPED":
            self.run_stats["processed"] += 1
            self.run_stats["skipped"] += 1
            
            await send_state()
            await send_log(event.get("patient_name", "Unknown"), "Patient Skipped", "skipped", event.get("reason", "Skipped"))
            
            matched = next((i for i in self.items if i["phone"] == event.get("phone") or i["patient_name"] == event.get("patient_name")), None)
            
            if matched:
                try:
                    await db.appointments.update_one(
                        {"_id": ObjectId(matched["appointmentId"])},
                        {"$set": {"reminderStatus": "SKIPPED", "updatedAt": datetime.utcnow()}}
                    )
                except Exception:
                    pass
                    
            await emit_workspace_event(workspace_id, "automation:skipped", {
                "runId": run_id,
                "patientName": event.get("patient_name"),
                "reason": event.get("reason")
            })

    async def _finalize_run(self, code, csv_path, workspace_id):
        self.active_process = None
        
        if os.path.exists(csv_path):
            try:
                os.remove(csv_path)
            except:
                pass
                
        db = get_db()
        final_status = "COMPLETED" if code == 0 else "FAILED"
        
        await emit_workspace_event(workspace_id, "state_update", {
            "state": {
                "status": final_status.lower(),
                "completedAt": datetime.utcnow().isoformat(),
                "currentPatient": None
            }
        })
        
        await emit_workspace_event(workspace_id, "log", {
            "log": {
                "patient": "System",
                "action": "Run Finished",
                "status": "success" if code == 0 else "failed",
                "message": f"Automation run finished with code {code} ({final_status}). Processed: {self.run_stats['processed']}/{self.run_stats['total']}",
                "time": datetime.utcnow().isoformat()
            }
        })
        
        await emit_workspace_event(workspace_id, "automation:confirming", {"runId": self.current_run_id})
        
        await db.automation_runs.update_one(
            {"_id": ObjectId(self.current_run_id)},
            {"$set": {
                "status": final_status,
                "completedAt": datetime.utcnow(),
                "totalProcessed": self.run_stats["processed"],
                "totalSent": self.run_stats["sent"],
                "totalConfirmed": self.run_stats["confirmed"],
                "totalFailed": self.run_stats["failed"],
                "totalSkipped": self.run_stats["skipped"]
            }}
        )
        
        await emit_workspace_event(workspace_id, f"automation:{final_status.lower()}", {
            "runId": self.current_run_id,
            "code": code
        })

    def stop_run(self, workspace_id):
        if not self.active_process:
            return False
        try:
            self.active_process.kill()
        except:
            pass
        self.active_process = None
        asyncio.create_task(emit_workspace_event(workspace_id, "state_update", {"state": {"status": "stopped", "currentPatient": None}}))
        asyncio.create_task(emit_workspace_event(workspace_id, "automation:stopped", {"runId": self.current_run_id}))
        return True

automation_worker = AutomationWorkerBridge()
