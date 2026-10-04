import csv
from pathlib import Path
from typing import Set

from core.config import REMINDER_LOG_PATH
from automation.models import Appointment, ProcessStatus, ProcessResult
from automation.validation import generate_dedup_key

LOG_COLUMNS = [
    "timestamp",
    "patient_name",
    "phone",
    "appointment_date",
    "appointment_time",
    "status",
    "error",
    "message_hash",
    "dedup_key",
]


class DeduplicationManager:
    def __init__(self, log_path: Path = REMINDER_LOG_PATH):
        self.log_path = log_path
        self._ensure_log_file_exists()

    def _ensure_log_file_exists(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            with open(self.log_path, mode="w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(LOG_COLUMNS)

    def get_sent_keys(self) -> Set[str]:
        sent_keys = set()
        if not self.log_path.exists():
            return sent_keys

        # Read errors propagate: treating an unreadable log as "nothing sent" would resend reminders.
        with open(self.log_path, mode="r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status", "").strip() != ProcessStatus.SENT.value:
                    continue
                key = row.get("dedup_key", "").strip() or generate_dedup_key(
                    row.get("phone", ""), row.get("appointment_date", ""), row.get("appointment_time", "")
                )
                if key:
                    sent_keys.add(key)
        return sent_keys

    def is_already_sent(self, appointment: Appointment) -> bool:
        return appointment.dedup_key in self.get_sent_keys()

    def log_result(self, result: ProcessResult):
        self._ensure_log_file_exists()
        with open(self.log_path, mode="a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                result.timestamp,
                result.appointment.patient_name,
                result.appointment.phone,
                result.appointment.appointment_date,
                result.appointment.appointment_time,
                result.status.value,
                result.error or "",
                result.message_hash or "",
                result.appointment.dedup_key,
            ])
