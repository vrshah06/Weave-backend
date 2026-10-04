from fastapi import APIRouter

from routes import appointment_routes, automation_routes, health_routes, import_routes, patient_routes, settings_routes

api_router = APIRouter()
for module in (health_routes, import_routes, appointment_routes, automation_routes, patient_routes, settings_routes):
    api_router.include_router(module.router)
