from datetime import datetime

from models.common import ApiModel


class PatientResponse(ApiModel):
    id: str
    full_name: str
    first_name: str
    last_name: str
    phone: str
    created_at: datetime
