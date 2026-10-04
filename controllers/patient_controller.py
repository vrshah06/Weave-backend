from services import patient_service


async def list_patients() -> list:
    return await patient_service.list_patients()


async def get_history(patient_id: str) -> list:
    return await patient_service.get_message_history(patient_id)
