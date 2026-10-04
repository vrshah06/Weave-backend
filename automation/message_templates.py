import hashlib
from core.config import DEFAULT_MESSAGE_TEMPLATE, BUSINESS_NAME


def generate_message(
    patient_name: str,
    appointment_date: str,
    appointment_time: str,
    template: str = None,
    business_name: str = BUSINESS_NAME,
) -> str:
    tmpl = template or DEFAULT_MESSAGE_TEMPLATE
    return tmpl.format(
        patient_name=patient_name,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        business_name=business_name,
    )


def hash_message(message_text: str) -> str:
    return hashlib.sha256(message_text.strip().encode("utf-8")).hexdigest()
