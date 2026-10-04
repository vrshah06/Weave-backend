from fastapi import APIRouter, Request

from controllers import automation_controller

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/status")
async def get_status():
    return await automation_controller.get_status()


@router.get("/logs")
async def get_logs():
    return automation_controller.get_logs()


@router.get("/events")
async def stream_events(request: Request):
    return automation_controller.stream_events(request)


@router.post("/start")
async def start_run(payload: dict):
    return await automation_controller.start_run(payload)


@router.post("/stop")
async def stop_run():
    return automation_controller.stop_run()


@router.get("/runs")
async def list_runs():
    return await automation_controller.list_runs()


@router.get("/runs/{run_id}")
async def get_run_details(run_id: str):
    return await automation_controller.get_run_details(run_id)


@router.post("/retry")
async def retry(payload: dict):
    return await automation_controller.retry(payload)


@router.get("/confirmations/last")
async def get_last_run_confirmations():
    return await automation_controller.get_last_run_confirmations()


@router.post("/confirmations/verify")
async def verify_last_run_confirmations():
    return await automation_controller.verify_last_run_confirmations()
