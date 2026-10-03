import hashlib
from config import DEFAULT_MESSAGE_TEMPLATE, BUSINESS_NAME


def generate_message(
    patient_name: str,
    appointment_date: str,
    appointment_time: str,
    template: str = None,
    business_name: str = BUSINESS_NAME,
) -> str:
    """
    Generates an appointment reminder SMS message deterministically based on input parameters.
    """
    tmpl = template or DEFAULT_MESSAGE_TEMPLATE
    return tmpl.format(
        patient_name=patient_name,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        business_name=business_name,
    )


def hash_message(message_text: str) -> str:
    """
    Returns a SHA256 hash string of the generated message text for audit logs.
    """
    return hashlib.sha256(message_text.strip().encode("utf-8")).hexdigest()
