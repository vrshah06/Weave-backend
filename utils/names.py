from dataclasses import dataclass


@dataclass(frozen=True)
class PatientName:
    full_name: str
    first_name: str
    last_name: str
    name_key: str


def parse_patient_name(raw: str) -> PatientName:
    """Accepts 'Last, First' or 'First Last'; both produce the same name_key."""
    text = " ".join((raw or "").split())
    if not text:
        raise ValueError("Patient name is required")
    if "," in text:
        last, _, first = text.partition(",")
        first, last = first.strip(), last.strip()
    else:
        first, _, last = text.partition(" ")
    full_name = f"{first} {last}".strip()
    if not full_name:
        raise ValueError(f"Invalid patient name '{raw}'")
    return PatientName(full_name=full_name, first_name=first, last_name=last, name_key=full_name.lower())

