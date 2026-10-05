from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.config import DEFAULT_MESSAGE_TEMPLATE, config
from core.errors import InvalidRequestError
from repositories import settings_repository
from services.message_template import render_sample, validate_template


def _defaults() -> dict:
    return {
        "business_name": config.default_business_name,
        "message_template": DEFAULT_MESSAGE_TEMPLATE,
        "time_zone": config.default_time_zone,
    }


async def get_settings() -> dict:
    return await settings_repository.find() or _defaults()


async def update_settings(business_name: str, message_template: str, time_zone: str) -> dict:
    validate_template(message_template)
    try:
        ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise InvalidRequestError(f"Unknown time zone '{time_zone}'. Use an IANA name such as America/New_York.")
    return await settings_repository.save({
        "business_name": business_name.strip(),
        "message_template": message_template,
        "time_zone": time_zone,
    })


async def preview_message() -> str:
    settings = await get_settings()
    return render_sample(settings["message_template"], settings["business_name"])
