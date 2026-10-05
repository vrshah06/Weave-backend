from datetime import date

import pytest

from utils.appointment_csv import CsvFormatError, parse_appointment_csv
from utils.names import parse_patient_name
from utils.phone import mask_phone, national_number, normalize_phone
from utils.schedule import format_time_12h, parse_appointment_date, parse_appointment_time


@pytest.mark.parametrize("raw", ["772-637-9314", "(772) 637-9314", "+1 772 637 9314", "17726379314", "772.637.9314"])
def test_us_phone_formats_normalize_to_e164(raw):
    assert normalize_phone(raw) == "+17726379314"


@pytest.mark.parametrize("raw", ["", "12345", "072-637-9314", "772-037-9314", "abc"])
def test_invalid_phones_are_rejected(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_phone_helpers():
    assert national_number("+17726379314") == "7726379314"
    assert mask_phone("+17726379314") == "***9314"


def test_last_first_and_first_last_names_share_a_key():
    a, b = parse_patient_name("Doe, Jane"), parse_patient_name("  jane   DOE ")
    assert a.full_name == "Jane Doe" and a.first_name == "Jane" and a.last_name == "Doe"
    assert a.name_key == b.name_key == "jane doe"


def test_dates_and_times_normalize():
    assert parse_appointment_date("10/2/2026") == date(2026, 10, 2)
    assert parse_appointment_date("2026-10-02") == date(2026, 10, 2)
    assert parse_appointment_time("9:00 am") == parse_appointment_time("09:00") == "09:00"
    assert parse_appointment_time("1:30 PM") == "13:30"
    assert format_time_12h("13:30") == "1:30 PM"
    with pytest.raises(ValueError):
        parse_appointment_time("25:00")


def test_csv_parses_quoted_names_and_reports_bad_rows():
    parsed = parse_appointment_csv(
        'Patient Name,Mobile,Appt Date,Appt Time\n"Doe, Jane",772-637-9314,10/02/2026,9:00 AM\nBad,123,10/02/2026,9:00 AM\n'
    )
    assert parsed.row_count == 2
    assert [r.patient.full_name for r in parsed.rows] == ["Jane Doe"]
    assert parsed.errors[0].row_number == 3 and "phone" in parsed.errors[0].message


def test_csv_without_required_columns_is_rejected():
    with pytest.raises(CsvFormatError, match="missing column"):
        parse_appointment_csv("name,phone\nJane,7726379314\n")
