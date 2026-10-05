from fastapi import APIRouter

from controllers import settings_controller
from models.settings_models import MessagePreviewResponse, SettingsResponse, SettingsUpdateRequest

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings():
    return await settings_controller.get_settings()


@router.put("", response_model=SettingsResponse, summary="Replace clinic settings; the message template is validated")
async def update_settings(request: SettingsUpdateRequest):
    return await settings_controller.update_settings(request)


@router.get("/message-preview", response_model=MessagePreviewResponse, summary="The template rendered with sample values")
async def preview_message():
    return await settings_controller.preview_message()
