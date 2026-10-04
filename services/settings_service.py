from repositories import settings_repository

DEFAULT_SETTINGS = {
    "name": "Default Medical Clinic",
    "messageTemplate": "Hi {{patient_name}}, reminder on {{appointment_date}} at {{appointment_time}}.",
    "timeZone": "America/New_York"
}


async def get_settings() -> dict:
    settings = await settings_repository.find()
    if not settings:
        await settings_repository.create(DEFAULT_SETTINGS)
        settings = await settings_repository.find()
    return settings


async def update_settings(name, message_template, time_zone) -> dict:
    await settings_repository.upsert({
        "name": name,
        "messageTemplate": message_template,
        "timeZone": time_zone
    })
    return await settings_repository.find()
