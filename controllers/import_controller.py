from fastapi import UploadFile

from services import import_service


async def import_csv(file: UploadFile) -> dict:
    content = (await file.read()).decode("utf-8")
    result = await import_service.import_appointments_csv(content)
    return {"message": "CSV import completed successfully", **result}
