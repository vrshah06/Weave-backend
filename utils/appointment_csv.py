import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from utils.names import PatientName, parse_patient_name
from utils.phone import normalize_phone
from utils.schedule import parse_appointment_date, parse_appointment_time

MAX_ROWS = 5000

COLUMN_KEYWORDS = {
    "patient_name": ("patient_name", "name", "patient"),
    "phone": ("phone", "mobile", "cell"),
    "appointment_date": ("appointment_date", "date"),
    "appointment_time": ("appointment_time", "time"),
    "provider": ("provider", "doctor"),
}
REQUIRED_COLUMNS = ("patient_name", "phone", "appointment_date", "appointment_time")


class CsvFormatError(ValueError):
    pass


@dataclass(frozen=True)
class AppointmentRow:
    row_number: int
    patient: PatientName
    phone: str
    phone_raw: str
    appointment_date: date
    appointment_time: str
    provider: str


@dataclass(frozen=True)
class RowError:
    row_number: int
    message: str


@dataclass
class ParsedAppointmentCsv:
    rows: list[AppointmentRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    row_count: int = 0


def decode_csv_bytes(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvFormatError("File is not valid UTF-8 or Windows-1252 text")


def _resolve_columns(headers: list[str]) -> dict[str, int]:
    normalized = [re.sub(r"[^a-z0-9_]", "", h.strip().lower().replace(" ", "_")) for h in headers]
    columns: dict[str, int] = {}
    for column, keywords in COLUMN_KEYWORDS.items():
        for keyword in keywords:
            index = next((i for i, h in enumerate(normalized) if keyword in h and i not in columns.values()), None)
            if index is not None:
                columns[column] = index
                break
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise CsvFormatError(f"CSV header is missing column(s): {', '.join(missing)}. Found: {', '.join(headers)}")
    return columns


def _cell(values: list[str], index: Optional[int]) -> str:
    return values[index].strip() if index is not None and index < len(values) else ""


def parse_appointment_csv(text: str) -> ParsedAppointmentCsv:
    records = [r for r in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in r)]
    if not records:
        raise CsvFormatError("CSV file is empty")
    columns = _resolve_columns(records[0])
    data_records = records[1:]
    if len(data_records) > MAX_ROWS:
        raise CsvFormatError(f"CSV has {len(data_records)} rows; the maximum is {MAX_ROWS}")

    result = ParsedAppointmentCsv(row_count=len(data_records))
    for row_number, values in enumerate(data_records, start=2):
        try:
            phone_raw = _cell(values, columns["phone"])
            result.rows.append(AppointmentRow(
                row_number=row_number,
                patient=parse_patient_name(_cell(values, columns["patient_name"])),
                phone=normalize_phone(phone_raw),
                phone_raw=phone_raw,
                appointment_date=parse_appointment_date(_cell(values, columns["appointment_date"])),
                appointment_time=parse_appointment_time(_cell(values, columns["appointment_time"])),
                provider=_cell(values, columns.get("provider")),
            ))
        except ValueError as exc:
            result.errors.append(RowError(row_number=row_number, message=str(exc)))
    return result
