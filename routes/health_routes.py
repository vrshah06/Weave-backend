from fastapi import APIRouter

from controllers import health_controller
from models.health_models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Database and worker health (no API key required)")
async def get_health():
    return await health_controller.get_health()
