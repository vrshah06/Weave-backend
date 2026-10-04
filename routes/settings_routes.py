from fastapi import APIRouter

from controllers import settings_controller

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings():
    return await settings_controller.get_settings()


@router.patch("")
async def update_settings(payload: dict):
    return await settings_controller.update_settings(payload)
