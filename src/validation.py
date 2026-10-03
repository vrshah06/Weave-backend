import re
from typing import Dict, Any
from src.models import Appointment


def normalize_phone(phone_str: str) -> str:
    """
    Normalizes a phone number to a standard E.164 format (+1XXXXXXXXXX for 10/11 digit US numbers)
    without corrupting international codes.
    
    Examples:
        '7725796722'      -> '+17725796722'
        '17725796722'     -> '+17725796722'
        '+1 772 579 6722' -> '+17725796722'
        '(772) 579-6722'  -> '+17725796722'
    """
    if not phone_str:
        return ""

    # Remove whitespace, dashes, parentheses, dots
    cleaned = re.sub(r"[\s\-\(\)\.]", "", str(phone_str).strip())

    if cleaned.startswith("+"):
        digits = re.sub(r"\D", "", cleaned[1:])
        return f"+{digits}"

    digits = re.sub(r"\D", "", cleaned)

    # US 10-digit standard
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"

    # Return with leading plus if digits present
    return f"+{digits}" if digits else ""


def generate_dedup_key(normalized_phone: str, date_str: str, time_str: str) -> str:
    """
    Generates a deterministic unique key based on normalized phone + appointment date + time.
    """
    norm_phone = normalize_phone(normalized_phone)
    norm_date = str(date_str).strip().lower()
    norm_time = str(time_str).strip().lower()
    return f"{norm_phone}_{norm_date}_{norm_time}"


def validate_appointment_row(row: Dict[str, Any], row_index: int) -> Appointment:
    """
    Validates a CSV row dictionary and constructs an Appointment model instance.
    Raises ValueError if required fields are missing or invalid.
    """
    patient_name = str(row.get("patient_name", "")).strip()
    phone = str(row.get("phone", "")).strip()
    appointment_date = str(row.get("appointment_date", "")).strip()
    appointment_time = str(row.get("appointment_time", "")).strip()

    errors = []
    if not patient_name:
        errors.append("patient_name is required")
    if not phone:
        errors.append("phone is required")
    if not appointment_date:
        errors.append("appointment_date is required")
    if not appointment_time:
        errors.append("appointment_time is required")

    if errors:
        raise ValueError(f"Row {row_index} invalid: {', '.join(errors)}")

    norm_phone = normalize_phone(phone)
    if not norm_phone or len(re.sub(r"\D", "", norm_phone)) < 10:
        raise ValueError(f"Row {row_index} invalid phone number format: '{phone}'")

    dedup_key = generate_dedup_key(norm_phone, appointment_date, appointment_time)

    return Appointment(
        row_index=row_index,
        patient_name=patient_name,
        phone=phone,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        normalized_phone=norm_phone,
        dedup_key=dedup_key,
    )
