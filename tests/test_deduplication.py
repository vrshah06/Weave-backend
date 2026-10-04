import tempfile
from pathlib import Path
from automation.deduplication import DeduplicationManager
from automation.models import ProcessStatus, ProcessResult
from automation.validation import validate_appointment_row


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

        assert not manager.is_already_sent(appt)

        manager.log_result(
            ProcessResult(
                appointment=appt,
                status=ProcessStatus.SENT,
                message_hash="test_hash_123",
            )
        )

        new_manager = DeduplicationManager(log_path=tmp_csv)
        assert new_manager.is_already_sent(appt)
