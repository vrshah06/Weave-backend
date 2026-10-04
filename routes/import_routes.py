from fastapi import APIRouter, File, UploadFile

from controllers import import_controller

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/csv")
async def import_csv(file: UploadFile = File(...)):
    return await import_controller.import_csv(file)
