import asyncio

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from core.exceptions import AutomationAlreadyRunningError, NoAppointmentsSelectedError
from core.event_stream import subscribe, unsubscribe
from services import automation_service
from automation.logging_utils import setup_logger

logger = setup_logger("weave_api")


async def get_status() -> dict:
    return await automation_service.get_status()


def get_logs() -> list:
    return []


def stream_events(request: Request) -> StreamingResponse:
    q = subscribe()

    async def event_generator():
        try:
            while not await request.is_disconnected():
                yield await q.get()
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def start_run(payload: dict) -> dict:
    try:
        res = await automation_service.start_run(payload.get("mode", "dry_run"), payload.get("date"), payload.get("targetIds"))
    except (AutomationAlreadyRunningError, NoAppointmentsSelectedError):
        raise
    except Exception:
        logger.exception("Failed to start automation run")
        raise HTTPException(status_code=500, detail="Failed to start automation run")
    return {"message": "Automation run started", **res}


def stop_run() -> dict:
    automation_service.stop_run()
    return {"message": "Stop command issued"}


async def retry(payload: dict) -> dict:
    res = await automation_service.retry_appointments(payload.get("appointmentIds", []), payload.get("mode", "send"))
    return {"message": "Retry job created", **res}


async def list_runs() -> list:
    return await automation_service.list_runs()


async def get_run_details(run_id: str) -> dict:
    return await automation_service.get_run_details(run_id)


async def get_last_run_confirmations() -> dict:
    return await automation_service.get_last_run_confirmations()


async def verify_last_run_confirmations() -> dict:
    result = await automation_service.verify_last_run_confirmations()
    return {"message": "Checked and verified all patient confirmations for the latest run successfully!", **result}
