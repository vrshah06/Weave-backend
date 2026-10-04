from datetime import datetime


def parse_time_to_minutes(time_str: str) -> int:
    if not time_str: return 0
    cleaned = time_str.strip().upper()
    try:
        dt = datetime.strptime(cleaned, "%I:%M %p")
        return dt.hour * 60 + dt.minute
    except ValueError:
        try:
            dt = datetime.strptime(cleaned, "%H:%M")
            return dt.hour * 60 + dt.minute
        except ValueError:
            return 0


def mask_phone(phone: str) -> str:
    if not phone: return ""
    digits = ''.join(filter(str.isdigit, phone))
    if len(digits) >= 4:
        return "***" + digits[-4:]
    return phone
