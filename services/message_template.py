import re
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

PLACEHOLDER_NORMALIZATIONS = {
    r"\{\s*patient[\s_]+name\s*\}": "{patient_name}",
    r"\{\s*first[\s_]+name\s*\}": "{first_name}",
    r"\{\s*last[\s_]+name\s*\}": "{last_name}",
    r"\{\s*appointment[\s_]+date\s*\}": "{appointment_date}",
    r"\{\s*appointment[\s_]+time\s*\}": "{appointment_time}",
    r"\{\s*provider\s*\}": "{provider}",
    r"\{\s*business[\s_]+name\s*\}": "{business_name}",
}


def normalize_template(template: str) -> str:
    normalized = template
    for pattern, target in PLACEHOLDER_NORMALIZATIONS.items():
        normalized = re.sub(pattern, target, normalized, flags=re.IGNORECASE)
    return normalized


def validate_template(template: str) -> None:
    norm_template = normalize_template(template)
    try:
        placeholders = [(name, spec, conv) for _, name, spec, conv in string.Formatter().parse(norm_template) if name is not None]
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
    norm_template = normalize_template(template)
    full_name = patient.get("full_name") or f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
    return norm_template.format(
        patient_name=full_name,
        first_name=patient.get("first_name", ""),
        last_name=patient.get("last_name", ""),
        appointment_date=format_date_us(appointment_date),
        appointment_time=format_time_12h(appointment_time),
        provider=provider,
        business_name=business_name,
    ).strip()


def render_sample(template: str, business_name: str) -> str:
    norm_template = normalize_template(template)
    return norm_template.format(**{**SAMPLE_VALUES, "business_name": business_name}).strip()
