import asyncio
import json
import os
import subprocess
import sys
import threading
from datetime import datetime

from bson import ObjectId

from core.config import BASE_DIR, DATA_DIR
from core.exceptions import AutomationAlreadyRunningError, NoAppointmentsSelectedError, NoActiveRunError
from core.event_stream import publish_event
from repositories import appointment_repository, automation_run_repository, message_attempt_repository, patient_repository
from automation.logging_utils import setup_logger

logger = setup_logger("weave_api")


class AutomationRunner:
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

    async def export_database_to_payload(self, appointment_date, target_ids=None):
        query = {}

        if not appointment_date and not target_ids:
            appointment_date = datetime.now().strftime("%Y-%m-%d")

        if appointment_date:
            query["appointmentDate"] = appointment_date

        if target_ids:
            query["_id"] = {"$in": [ObjectId(tid) if isinstance(tid, str) and len(tid) == 24 else tid for tid in target_ids]}

        appointments = await appointment_repository.list_by_query(query)

        valid_items = []
        for appt in appointments:
            if appt.get("reminderStatus") in ["CONFIRMED", "SENT", "SKIPPED"] and not target_ids:
                continue

            if not appt.get("reminderSelected", True) and not target_ids:
                continue

            patient = await patient_repository.find_by_id(appt.get("patientId"))
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

        csv_path = os.path.join(DATA_DIR, f"temp_run_{int(datetime.now().timestamp()*1000)}.csv")

        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("patient_name,phone,appointment_date,appointment_time,provider\n")
            for item in valid_items:
                f.write(f'"{item["patient_name"]}","{item["phone"]}","{item["appointment_date"]}","{item["appointment_time"]}","{item["provider"]}"\n')

        return csv_path, len(valid_items), valid_items

    async def execute_run(self, appointment_date=None, mode="dry_run", target_ids=None):
        if self.active_process:
            raise AutomationAlreadyRunningError()

        csv_path, count, self.items = await self.export_database_to_payload(appointment_date, target_ids)

        if count == 0:
            raise NoAppointmentsSelectedError()

        self.run_stats = {
            "processed": 0, "sent": 0, "confirmed": 0,
            "failed": 0, "skipped": 0, "total": count
        }

        run_record = {
            "appointmentDate": appointment_date or datetime.now().strftime("%Y-%m-%d"),
            "mode": mode,
            "status": "STARTING",
            "totalSelected": count,
            "startedAt": datetime.utcnow()
        }

        self.current_run_id = str(await automation_run_repository.create(run_record))

        await publish_event("state_update", {
            "state": {
                "status": "starting",
                "mode": mode,
                "total": count,
                "remaining": count,
                "startedAt": datetime.utcnow().isoformat()
            }
        })

        await publish_event("automation:started", {
            "runId": self.current_run_id,
            "mode": mode,
            "total": count,
            "date": appointment_date
        })

        mode_flag = "--send" if mode == "send" else "--dry-run"
        args = ["run_reminders.py", mode_flag, "--file", csv_path]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        self.active_process = subprocess.Popen(
            [sys.executable, *args],
            cwd=BASE_DIR,
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
                asyncio.run_coroutine_threadsafe(self._process_line(line, self.current_run_id, is_stderr), loop)

        def wait_process():
            code = self.active_process.wait()
            asyncio.run_coroutine_threadsafe(self._finalize_run(code, csv_path), loop)

        threading.Thread(target=pump_stream, args=(self.active_process.stdout, False), daemon=True).start()
        threading.Thread(target=pump_stream, args=(self.active_process.stderr, True), daemon=True).start()
        threading.Thread(target=wait_process, daemon=True).start()

        return {"runId": self.current_run_id, "count": count, "mode": mode}

    async def _process_line(self, decoded, run_id, is_stderr):
        try:
            if "[EVENT]" in decoded:
                event = json.loads(decoded.split("[EVENT]", 1)[1])
                await self._process_event(event, run_id)
            else:
                await publish_event("log", {
                    "log": {
                        "patient": "System",
                        "action": "Console Log",
                        "status": "running" if not is_stderr else "failed",
                        "message": decoded,
                        "time": datetime.utcnow().isoformat()
                    }
                })
        except Exception:
            logger.exception("Failed to process automation output line")

    def _match_item(self, event):
        return next((i for i in self.items if i["phone"] == event.get("phone") or i["patient_name"] == event.get("patient_name")), None)

    async def _record_attempt(self, run_id, matched, status, fields):
        try:
            appointment_id = ObjectId(matched["appointmentId"])
            await appointment_repository.update_status(appointment_id, status)
            attempt_count = await message_attempt_repository.count_by_appointment(appointment_id)
            await message_attempt_repository.create({
                "patientId": ObjectId(matched["patientId"]),
                "appointmentId": appointment_id,
                "automationRunId": ObjectId(run_id),
                "attemptNumber": attempt_count + 1,
                "status": status,
                **fields
            })
        except Exception:
            logger.exception("Failed to record %s attempt for appointment %s", status, matched["appointmentId"])

    async def _process_event(self, event, run_id):
        event_type = event.get("type")

        async def send_state():
            await publish_event("state_update", {
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
            await publish_event("log", {
                "log": {
                    "patient": patient,
                    "action": action,
                    "status": status,
                    "message": message,
                    "time": datetime.utcnow().isoformat()
                }
            })

        if event_type == "PATIENT_START":
            await publish_event("automation:patient", {
                "runId": run_id,
                "patientName": event.get("patient_name"),
                "phone": event.get("phone"),
                "position": event.get("position")
            })
            await publish_event("state_update", {
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

            matched = self._match_item(event)
            if matched:
                status = "SENT" if is_sent else "CONFIRMED"
                await self._record_attempt(run_id, matched, status, {
                    "message": f"Appointment reminder for {matched['appointment_date']} at {matched['appointment_time']}",
                    "sentAt": datetime.utcnow(),
                    "confirmedAt": None if is_sent else datetime.utcnow()
                })

            await publish_event("automation:sent", {
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

            matched = self._match_item(event)
            if matched:
                await self._record_attempt(run_id, matched, "FAILED", {
                    "failureReason": event.get("reason", "Not Delivered"),
                    "failedAt": datetime.utcnow()
                })

            await publish_event("automation:failed", {
                "runId": run_id,
                "patientName": event.get("patient_name"),
                "reason": event.get("reason")
            })

        elif event_type == "PATIENT_SKIPPED":
            self.run_stats["processed"] += 1
            self.run_stats["skipped"] += 1

            await send_state()
            await send_log(event.get("patient_name", "Unknown"), "Patient Skipped", "skipped", event.get("reason", "Skipped"))

            matched = self._match_item(event)
            if matched:
                try:
                    await appointment_repository.update_status(ObjectId(matched["appointmentId"]), "SKIPPED")
                except Exception:
                    logger.exception("Failed to record skipped appointment %s", matched["appointmentId"])

            await publish_event("automation:skipped", {
                "runId": run_id,
                "patientName": event.get("patient_name"),
                "reason": event.get("reason")
            })

    async def _finalize_run(self, code, csv_path):
        self.active_process = None

        if os.path.exists(csv_path):
            try:
                os.remove(csv_path)
            except OSError:
                logger.warning("Could not remove temporary run file %s", csv_path)

        final_status = "COMPLETED" if code == 0 else "FAILED"

        await publish_event("state_update", {
            "state": {
                "status": final_status.lower(),
                "completedAt": datetime.utcnow().isoformat(),
                "currentPatient": None
            }
        })

        await publish_event("log", {
            "log": {
                "patient": "System",
                "action": "Run Finished",
                "status": "success" if code == 0 else "failed",
                "message": f"Automation run finished with code {code} ({final_status}). Processed: {self.run_stats['processed']}/{self.run_stats['total']}",
                "time": datetime.utcnow().isoformat()
            }
        })

        await publish_event("automation:confirming", {"runId": self.current_run_id})

        await automation_run_repository.update(self.current_run_id, {
            "status": final_status,
            "completedAt": datetime.utcnow(),
            "totalProcessed": self.run_stats["processed"],
            "totalSent": self.run_stats["sent"],
            "totalConfirmed": self.run_stats["confirmed"],
            "totalFailed": self.run_stats["failed"],
            "totalSkipped": self.run_stats["skipped"]
        })

        await publish_event(f"automation:{final_status.lower()}", {
            "runId": self.current_run_id,
            "code": code
        })

    def stop_run(self):
        if not self.active_process:
            raise NoActiveRunError()
        try:
            self.active_process.kill()
        except OSError:
            logger.warning("Automation process had already exited")
        self.active_process = None
        asyncio.create_task(publish_event("state_update", {"state": {"status": "stopped", "currentPatient": None}}))
        asyncio.create_task(publish_event("automation:stopped", {"runId": self.current_run_id}))


automation_runner = AutomationRunner()
