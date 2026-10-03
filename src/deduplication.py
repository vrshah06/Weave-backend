import csv
from datetime import datetime
from pathlib import Path
from typing import Set, Optional
from config import REMINDER_LOG_PATH
from src.models import Appointment, ProcessStatus, ProcessResult
from src.validation import generate_dedup_key


class DeduplicationManager:
    """
    Manages persistent send logs and prevents sending duplicate reminders to patients.
    """

    def __init__(self, log_path: Path = REMINDER_LOG_PATH):
        self.log_path = log_path
        self._ensure_log_file_exists()

    def _ensure_log_file_exists(self):
        """
        Creates the reminder_log.csv file with headers if it does not already exist.
        """
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            with open(self.log_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "patient_name",
                    "phone",
                    "appointment_date",
                    "appointment_time",
                    "status",
                    "error",
                    "message_hash",
                    "dedup_key",
                ])

    def get_sent_keys(self) -> Set[str]:
        """
        Reads existing logs and returns set of dedup keys that were SENT successfully.
        """
        sent_keys = set()
        if not self.log_path.exists():
            return sent_keys

        try:
            with open(self.log_path, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    status = row.get("status", "").strip()
                    # Only record SENT reminders as completed
                    if status == ProcessStatus.SENT.value:
                        key = row.get("dedup_key", "").strip()
                        if not key:
                            # Fallback generate key
                            phone = row.get("phone", "")
                            date = row.get("appointment_date", "")
                            time = row.get("appointment_time", "")
                            key = generate_dedup_key(phone, date, time)
                        if key:
                            sent_keys.add(key)
        except Exception as e:
            pass

        return sent_keys

    def is_already_sent(self, appointment: Appointment) -> bool:
        """
        Checks if the exact appointment reminder has already been successfully sent.
        """
        return appointment.dedup_key in self.get_sent_keys()

    def log_result(self, result: ProcessResult):
        """
        Appends a process result to the persistent reminder_log.csv file.
        """
        self._ensure_log_file_exists()
        timestamp = result.timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(self.log_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp,
                result.appointment.patient_name,
                result.appointment.phone,
                result.appointment.appointment_date,
                result.appointment.appointment_time,
                result.status.value,
                result.error or "",
                result.message_hash or "",
                result.appointment.dedup_key,
            ])
