from datetime import datetime
from typing import Literal, Optional

from models.common import ApiModel


class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    database: Literal["up", "down"]
    worker: Literal["online", "offline", "unknown"]
    worker_heartbeat_at: Optional[datetime] = None
    checked_at: datetime
