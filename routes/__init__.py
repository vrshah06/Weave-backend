from fastapi import APIRouter, Depends

from core.security import require_api_key
from routes import appointment_routes, health_routes, import_routes, patient_routes, run_routes, settings_routes

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_routes.router)
api_router.include_router(run_routes.router)
for module in (import_routes, appointment_routes, patient_routes, settings_routes):
    api_router.include_router(module.router, dependencies=[Depends(require_api_key)])
