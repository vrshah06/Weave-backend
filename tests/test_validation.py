import pytest
from src.validation import normalize_phone, generate_dedup_key, validate_appointment_row


def test_normalize_phone():
    assert normalize_phone("7725796722") == "+17725796722"
    assert normalize_phone("17725796722") == "+17725796722"
    assert normalize_phone("+1 772 579 6722") == "+17725796722"
    assert normalize_phone("(772) 579-6722") == "+17725796722"
    assert normalize_phone("+17725796722") == "+17725796722"
    assert normalize_phone("") == ""


def test_generate_dedup_key():
    key1 = generate_dedup_key("(772) 579-6722", "09/21/2026", "10:00 AM")
    key2 = generate_dedup_key("+17725796722", "09/21/2026", "10:00 AM")
    assert key1 == key2
    assert key1 == "+17725796722_09/21/2026_10:00 am"


def test_validate_appointment_row_success():
    row = {
        "patient_name": "James Laterra",
        "phone": "+17725796722",
        "appointment_date": "09/21/2026",
        "appointment_time": "10:00 AM",
    }
    appt = validate_appointment_row(row, 1)
    assert appt.patient_name == "James Laterra"
    assert appt.normalized_phone == "+17725796722"
    assert appt.row_index == 1


def test_validate_appointment_row_missing_field():
    row = {
        "patient_name": "James Laterra",
        "phone": "",
        "appointment_date": "09/21/2026",
        "appointment_time": "10:00 AM",
    }
    with pytest.raises(ValueError, match="phone is required"):
        validate_appointment_row(row, 2)
