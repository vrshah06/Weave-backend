from pydantic import Field

from models.common import ApiModel


class SettingsResponse(ApiModel):
    business_name: str
    message_template: str
    time_zone: str


class SettingsUpdateRequest(ApiModel):
    business_name: str = Field(min_length=1, max_length=200)
    message_template: str = Field(min_length=1, max_length=1600)
    time_zone: str = Field(min_length=1, max_length=64)


class MessagePreviewResponse(ApiModel):
    message: str
