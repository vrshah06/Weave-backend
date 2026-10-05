from fastapi import APIRouter, File, Query, UploadFile

from controllers import import_controller
from models.common import Page
from models.import_models import ImportResponse, ImportSummaryResponse

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("", response_model=ImportResponse, status_code=201,
             summary="Import an appointment CSV; syncs each date in the file (rows missing for that date are cancelled)")
async def create_import(file: UploadFile = File(...)):
    return await import_controller.create_import(file)


@router.get("", response_model=Page[ImportSummaryResponse])
async def list_imports(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await import_controller.list_imports(limit, offset)


@router.get("/{import_id}", response_model=ImportResponse)
async def get_import(import_id: str):
    return await import_controller.get_import(import_id)
