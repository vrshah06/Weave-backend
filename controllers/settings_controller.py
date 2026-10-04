from services import settings_service


async def get_settings() -> dict:
    return await settings_service.get_settings()


async def update_settings(payload: dict) -> dict:
    return await settings_service.update_settings(payload.get("name"), payload.get("messageTemplate"), payload.get("timeZone"))
