import re
from datetime import datetime

HEADER_KEYWORDS = {
    "patient_name": ("name", "patient"),
    "phone": ("phone", "mobile", "cell"),
    "appointment_date": ("date",),
    "appointment_time": ("time",),
    "provider": ("provider", "doctor"),
}
DEFAULT_COLUMNS = {"patient_name": 0, "phone": 1, "appointment_date": 2, "appointment_time": 3}


def parse_csv_line(line: str) -> list[str]:
    result = []
    current = ""
    in_quotes = False
    for char in line:
        if char in ('"', "'"):
            in_quotes = not in_quotes
        elif char == ',' and not in_quotes:
            result.append(current.strip().strip("'\""))
            current = ""
        else:
            current += char
    result.append(current.strip().strip("'\""))
    return result


def normalize_date_to_iso(date_str: str) -> str:
    if not date_str:
        return datetime.now().date().isoformat()
    parts = re.split(r'[\/-]', date_str.strip())
    if len(parts) == 3:
        m, d, y = parts[0].zfill(2), parts[1].zfill(2), parts[2]
        if len(y) == 2:
            y = "20" + y
        return f"{y}-{m}-{d}"
    return date_str


def split_patient_name(raw_name: str) -> tuple[str, str]:
    if ',' in raw_name:
        last, _, first = raw_name.partition(',')
        return first.strip(), last.strip()
    parts = raw_name.strip().split()
    return (parts[0] if parts else ""), " ".join(parts[1:])


def _map_headers(header_line: str) -> dict:
    headers = [re.sub(r'[^a-z0-9_]', '', h.lower()) for h in parse_csv_line(header_line)]
    columns = dict(DEFAULT_COLUMNS)
    for field, keywords in HEADER_KEYWORDS.items():
        for idx, h in enumerate(headers):
            if any(k in h for k in keywords):
                columns[field] = idx
    return columns


def parse_appointment_csv(csv_content: str) -> dict:
    lines = [l.strip() for l in csv_content.splitlines() if l.strip()]
    if not lines:
        return {"rows": [], "totalReceived": 0, "errors": ["CSV file is empty"]}

    columns = _map_headers(lines[0])

    valid_rows = []
    errors = []
    for i, line in enumerate(lines[1:], start=2):
        cols = parse_csv_line(line)
        value = {field: (cols[idx] if idx < len(cols) else "") for field, idx in columns.items()}
        value.setdefault("provider", "")

        if not all(value[f] for f in DEFAULT_COLUMNS):
            errors.append(f"Row {i} skipped: Missing required fields")
            continue

        first_name, last_name = split_patient_name(value["patient_name"])
        valid_rows.append({
            "rowIndex": i,
            "firstName": first_name,
            "lastName": last_name,
            "fullName": value["patient_name"].strip(),
            "phone": value["phone"].strip(),
            "appointmentDateIso": normalize_date_to_iso(value["appointment_date"]),
            "appointmentTime": value["appointment_time"].strip(),
            "provider": value["provider"].strip()
        })

    return {"rows": valid_rows, "totalReceived": len(lines) - 1, "errors": errors}
