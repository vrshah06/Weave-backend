from fastapi.responses import JSONResponse

from models.health_models import HealthResponse
from services import health_service


async def get_health() -> JSONResponse:
    health = HealthResponse(**await health_service.check())
    status_code = 200 if health.database == "up" else 503
    return JSONResponse(status_code=status_code, content=health.model_dump(mode="json", by_alias=True))
