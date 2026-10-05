from datetime import date, datetime

DATE_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y")
TIME_FORMATS = ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p", "%H:%M")


def parse_appointment_date(raw: str) -> date:
    text = (raw or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid appointment date '{raw}'. Use MM/DD/YYYY or YYYY-MM-DD.")


def parse_appointment_time(raw: str) -> str:
    """Return the time as 24-hour 'HH:MM' so '9:00 AM' and '09:00' are the same slot."""
    text = " ".join((raw or "").strip().upper().split())
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise ValueError(f"Invalid appointment time '{raw}'. Use e.g. 9:00 AM or 13:30.")


def format_time_12h(time_24h: str) -> str:
    return datetime.strptime(time_24h, "%H:%M").strftime("%I:%M %p").lstrip("0")


def format_date_us(value: date) -> str:
    return value.strftime("%m/%d/%Y")
