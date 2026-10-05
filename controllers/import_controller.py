from fastapi import UploadFile

from controllers.presenters import present_import, present_import_summary
from core.errors import InvalidRequestError
from models.common import Page
from models.import_models import ImportResponse, ImportSummaryResponse
from services import import_service

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


async def create_import(file: UploadFile) -> ImportResponse:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise InvalidRequestError("CSV file is larger than 5 MB")
    document = await import_service.import_appointments(file.filename or "upload.csv", content)
    return present_import(document)


async def list_imports(limit: int, offset: int) -> Page[ImportSummaryResponse]:
    documents, total = await import_service.list_page(limit, offset)
    return Page(items=[present_import_summary(d) for d in documents], total=total, limit=limit, offset=offset)


async def get_import(import_id: str) -> ImportResponse:
    return present_import(await import_service.get(import_id))
