from repositories import appointment_repository, message_attempt_repository, patient_repository


async def list_patients() -> list:
    patients = await patient_repository.list_all()
    for p in patients: p["_id"] = str(p["_id"])
    return patients


async def get_message_history(patient_id: str) -> list:
    history = await message_attempt_repository.list_by_patient(patient_id)
    for h in history:
        h["_id"] = str(h["_id"])
        if h.get("patientId"):
            h["patientId"] = str(h["patientId"])
        if h.get("automationRunId"):
            h["automationRunId"] = str(h["automationRunId"])

        if h.get("appointmentId"):
            appt = await appointment_repository.find_by_id(h["appointmentId"])
            if appt:
                h["appointmentId"] = {
                    "_id": str(appt["_id"]),
                    "appointmentDate": appt.get("appointmentDate"),
                    "appointmentTime": appt.get("appointmentTime"),
                    "provider": appt.get("provider")
                }
            else:
                h["appointmentId"] = str(h["appointmentId"])
    return history
