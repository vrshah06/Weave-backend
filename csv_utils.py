import re
from datetime import datetime

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
        m = parts[0].zfill(2)
        d = parts[1].zfill(2)
        y = parts[2]
        if len(y) == 2:
            y = "20" + y
        return f"{y}-{m}-{d}"
    return date_str

def normalize_date_to_display(date_str: str) -> str:
    if not date_str:
        return ""
    parts = re.split(r'[\/-]', date_str.strip())
    if len(parts) == 3:
        m = parts[0].zfill(2)
        d = parts[1].zfill(2)
        y = parts[2]
        if len(y) == 2:
            y = "20" + y
        return f"{m}/{d}/{y}"
    return date_str

def parse_appointment_csv(csv_content: str):
    lines = [l.strip() for l in csv_content.splitlines() if l.strip()]
    if not lines:
        return {"rows": [], "headers": [], "errors": ["CSV file is empty"]}
    
    raw_headers = [re.sub(r'[^a-z0-9_]', '', h.lower()) for h in parse_csv_line(lines[0])]
    header_map = {}
    for idx, h in enumerate(raw_headers):
        if 'name' in h or 'patient' in h:
            header_map['patient_name'] = idx
        if 'phone' in h or 'mobile' in h or 'cell' in h:
            header_map['phone'] = idx
        if 'date' in h:
            header_map['appointment_date'] = idx
        if 'time' in h:
            header_map['appointment_time'] = idx
        if 'provider' in h or 'doctor' in h:
            header_map['provider'] = idx
            
    if 'patient_name' not in header_map: header_map['patient_name'] = 0
    if 'phone' not in header_map: header_map['phone'] = 1
    if 'appointment_date' not in header_map: header_map['appointment_date'] = 2
    if 'appointment_time' not in header_map: header_map['appointment_time'] = 3
    
    valid_rows = []
    errors = []
    
    for i in range(1, len(lines)):
        cols = parse_csv_line(lines[i])
        raw_name = cols[header_map['patient_name']] if header_map.get('patient_name') < len(cols) else ""
        raw_phone = cols[header_map['phone']] if header_map.get('phone') < len(cols) else ""
        raw_date = cols[header_map['appointment_date']] if header_map.get('appointment_date') < len(cols) else ""
        raw_time = cols[header_map['appointment_time']] if header_map.get('appointment_time') < len(cols) else ""
        raw_provider = cols[header_map['provider']] if header_map.get('provider') is not None and header_map['provider'] < len(cols) else ""
        
        if not raw_name or not raw_phone or not raw_date or not raw_time:
            errors.append(f"Row {i + 1} skipped: Missing required fields")
            continue
            
        first_name = raw_name
        last_name = ""
        if ',' in raw_name:
            parts = raw_name.split(',')
            last_name = parts[0].strip()
            first_name = parts[1].strip() if len(parts) > 1 else ""
        else:
            parts = raw_name.strip().split()
            first_name = parts[0] if parts else ""
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
            
        iso_date = normalize_date_to_iso(raw_date)
        display_date = normalize_date_to_display(raw_date)
        
        valid_rows.append({
            "rowIndex": i + 1,
            "rawName": raw_name,
            "firstName": first_name,
            "lastName": last_name,
            "fullName": raw_name.strip(),
            "phone": raw_phone.strip(),
            "appointmentDateIso": iso_date,
            "appointmentDateDisplay": display_date,
            "appointmentTime": raw_time.strip(),
            "provider": raw_provider.strip()
        })
        
    return {"rows": valid_rows, "totalReceived": len(lines) - 1, "errors": errors}
