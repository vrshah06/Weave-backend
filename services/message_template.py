import string
from datetime import date

from core.errors import InvalidRequestError
from utils.schedule import format_date_us, format_time_12h

ALLOWED_PLACEHOLDERS = ("patient_name", "first_name", "last_name", "appointment_date", "appointment_time", "provider", "business_name")

SAMPLE_VALUES = {
    "patient_name": "Jane Doe",
    "first_name": "Jane",
    "last_name": "Doe",
    "appointment_date": "10/02/2026",
    "appointment_time": "9:00 AM",
    "provider": "Dr. Smith",
    "business_name": "Sample Clinic",
}


def validate_template(template: str) -> None:
    try:
        placeholders = [(name, spec, conv) for _, name, spec, conv in string.Formatter().parse(template) if name is not None]
    except ValueError as exc:
        raise InvalidRequestError(f"Message template has unbalanced braces: {exc}")
    unknown = sorted({name for name, _, _ in placeholders if name not in ALLOWED_PLACEHOLDERS})
    if unknown:
        raise InvalidRequestError(
            f"Unknown placeholder(s): {', '.join('{' + f + '}' for f in unknown)}. "
            f"Allowed: {', '.join('{' + f + '}' for f in ALLOWED_PLACEHOLDERS)}"
        )
    if any(spec or conv for _, spec, conv in placeholders):
        raise InvalidRequestError("Placeholders cannot use format specifiers, e.g. write {appointment_time}")


def render_message(template: str, *, patient: dict, appointment_date: date, appointment_time: str, provider: str, business_name: str) -> str:
    return template.format(
        patient_name=patient["full_name"],
        first_name=patient["first_name"],
        last_name=patient["last_name"],
        appointment_date=format_date_us(appointment_date),
        appointment_time=format_time_12h(appointment_time),
        provider=provider,
        business_name=business_name,
    ).strip()


def render_sample(template: str, business_name: str) -> str:
    return template.format(**{**SAMPLE_VALUES, "business_name": business_name}).strip()
