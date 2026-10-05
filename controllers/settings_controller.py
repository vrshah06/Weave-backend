from models.settings_models import MessagePreviewResponse, SettingsResponse, SettingsUpdateRequest
from services import settings_service


async def get_settings() -> SettingsResponse:
    return SettingsResponse(**await settings_service.get_settings())


async def update_settings(request: SettingsUpdateRequest) -> SettingsResponse:
    settings = await settings_service.update_settings(request.business_name, request.message_template, request.time_zone)
    return SettingsResponse(**settings)


async def preview_message() -> MessagePreviewResponse:
    return MessagePreviewResponse(message=await settings_service.preview_message())
