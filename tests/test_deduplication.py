import tempfile
from pathlib import Path
from src.deduplication import DeduplicationManager
from src.models import Appointment, ProcessStatus, ProcessResult
from src.validation import validate_appointment_row


def test_deduplication_manager():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_csv = Path(tmp_dir) / "test_reminder_log.csv"
        manager = DeduplicationManager(log_path=tmp_csv)

        row = {
            "patient_name": "James Laterra",
            "phone": "+17725796722",
            "appointment_date": "09/21/2026",
            "appointment_time": "10:00 AM",
        }
        appt = validate_appointment_row(row, 1)

        # Before logging -> should not be marked sent
        assert not manager.is_already_sent(appt)

        # Log SENT result
        manager.log_result(
            ProcessResult(
                appointment=appt,
                status=ProcessStatus.SENT,
                message_hash="test_hash_123",
            )
        )

        # Reload manager from CSV file -> should detect sent
        new_manager = DeduplicationManager(log_path=tmp_csv)
        assert new_manager.is_already_sent(appt)
