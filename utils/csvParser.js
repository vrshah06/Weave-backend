const parseCsvLine = (line) => {
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === '"' || char === "'") {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      result.push(current.trim().replace(/^["']|["']$/g, ''));
      current = '';
    } else {
      current += char;
    }
  }
  result.push(current.trim().replace(/^["']|["']$/g, ''));
  return result;
};

const normalizeDateToIso = (dateStr) => {
  if (!dateStr) return new Date().toISOString().split('T')[0];
  const parts = dateStr.trim().split(/[\/-]/);
  if (parts.length === 3) {
    let m = parts[0].padStart(2, '0');
    let d = parts[1].padStart(2, '0');
    let y = parts[2];
    if (y.length === 2) y = '20' + y;
    return `${y}-${m}-${d}`;
  }
  return dateStr;
};

const normalizeDateToDisplay = (dateStr) => {
  if (!dateStr) return '';
  const parts = dateStr.trim().split(/[\/-]/);
  if (parts.length === 3) {
    let m = parts[0].padStart(2, '0');
    let d = parts[1].padStart(2, '0');
    let y = parts[2];
    if (y.length === 2) y = '20' + y;
    return `${m}/${d}/${y}`;
  }
  return dateStr;
};

const parseAppointmentCsv = (csvContent) => {
  const lines = csvContent.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
  if (lines.length === 0) {
    return { rows: [], headers: [], errors: ["CSV file is empty"] };
  }

  const rawHeaders = parseCsvLine(lines[0]).map(h => h.toLowerCase().replace(/[^a-z0-9_]/g, ''));
  const headerMap = {};
  rawHeaders.forEach((h, idx) => {
    if (h.includes('name') || h.includes('patient')) headerMap['patient_name'] = idx;
    if (h.includes('phone') || h.includes('mobile') || h.includes('cell')) headerMap['phone'] = idx;
    if (h.includes('date')) headerMap['appointment_date'] = idx;
    if (h.includes('time')) headerMap['appointment_time'] = idx;
    if (h.includes('provider') || h.includes('doctor')) headerMap['provider'] = idx;
  });

  // Default header positions if unmapped
  if (headerMap['patient_name'] === undefined) headerMap['patient_name'] = 0;
  if (headerMap['phone'] === undefined) headerMap['phone'] = 1;
  if (headerMap['appointment_date'] === undefined) headerMap['appointment_date'] = 2;
  if (headerMap['appointment_time'] === undefined) headerMap['appointment_time'] = 3;

  const validRows = [];
  const errors = [];

  for (let i = 1; i < lines.length; i++) {
    const cols = parseCsvLine(lines[i]);
    const rawName = cols[headerMap['patient_name']] || '';
    const rawPhone = cols[headerMap['phone']] || '';
    const rawDate = cols[headerMap['appointment_date']] || '';
    const rawTime = cols[headerMap['appointment_time']] || '';
    const rawProvider = headerMap['provider'] !== undefined ? cols[headerMap['provider']] || '' : '';

    if (!rawName || !rawPhone || !rawDate || !rawTime) {
      errors.push(`Row ${i + 1} skipped: Missing required fields`);
      continue;
    }

    // Parse Name (Last, First or First Last)
    let firstName = rawName;
    let lastName = '';
    if (rawName.includes(',')) {
      const parts = rawName.split(',');
      lastName = parts[0].trim();
      firstName = parts[1].trim();
    } else {
      const parts = rawName.trim().split(/\s+/);
      firstName = parts[0] || '';
      lastName = parts.slice(1).join(' ') || '';
    }

    const isoDate = normalizeDateToIso(rawDate);
    const displayDate = normalizeDateToDisplay(rawDate);

    validRows.push({
      rowIndex: i + 1,
      rawName,
      firstName,
      lastName,
      fullName: rawName.trim(),
      phone: rawPhone.trim(),
      appointmentDateIso: isoDate,
      appointmentDateDisplay: displayDate,
      appointmentTime: rawTime.trim(),
      provider: rawProvider.trim()
    });
  }

  return { rows: validRows, totalReceived: lines.length - 1, errors };
};

module.exports = { parseAppointmentCsv, normalizeDateToIso, normalizeDateToDisplay };
