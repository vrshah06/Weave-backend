from datetime import date, datetime
from typing import AsyncIterator, Optional
from zoneinfo import ZoneInfo

from bson import ObjectId

from core.errors import ConflictError, InvalidRequestError, NotFoundError
from models.enums import RunMode, RunStatus
from repositories import appointment_repository, run_item_repository, run_log_repository, run_repository, screenshot_repository
from services import settings_service
from utils.object_ids import parse_body_ids, parse_path_id


async def create_run(appointment_date: date, mode: RunMode) -> dict:
    settings = await settings_service.get_settings()
    today = datetime.now(ZoneInfo(settings["time_zone"])).date()
    if appointment_date < today:
        raise InvalidRequestError(f"Cannot start a run for a past date ({appointment_date.isoformat()}); today is {today.isoformat()}")

    active = await run_repository.find_active_for_date(appointment_date)
    if active:
        raise ConflictError(
            f"Run {active['_id']} for {appointment_date.isoformat()} is already {active['status']}",
            details={"runId": str(active["_id"])},
        )
    if await appointment_repository.count_runnable(appointment_date) == 0:
        raise InvalidRequestError(f"No pending, non-excluded appointments on {appointment_date.isoformat()}")
    return await run_repository.create(appointment_date, mode)


async def get(run_id: str) -> dict:
    run = await run_repository.find_by_id(parse_path_id(run_id, "Run"))
    if not run:
        raise NotFoundError("Run not found")
    return run


async def get_latest() -> dict:
    run = await run_repository.find_latest()
    if not run:
        raise NotFoundError("No runs found")
    return run


async def list_page(status: Optional[RunStatus], limit: int, offset: int) -> tuple[list[dict], int]:
    return await run_repository.list_page(status, limit, offset)


async def stop(run_id: str) -> dict:
    run = await get(run_id)
    updated = await run_repository.cancel_if_queued(run["_id"]) or await run_repository.request_stop_if_running(run["_id"])
    if updated:
        return updated
    current = await run_repository.find_by_id(run["_id"]) or run
    raise ConflictError(f"Run is already {current['status']} and cannot be stopped")


async def list_items(run_id: str) -> list[dict]:
    run = await get(run_id)
    return await run_item_repository.list_for_run_with_details(run["_id"])


async def list_logs(run_id: str, after_id: Optional[str], limit: int) -> list[dict]:
    run = await get(run_id)
    after = parse_body_ids([after_id], "after")[0] if after_id else None
    return await run_log_repository.list_after(run["_id"], after, limit)


async def open_screenshot(run_id: str, screenshot_id: str) -> AsyncIterator[bytes]:
    run = await get(run_id)
    stream = await screenshot_repository.open_for_run(run["_id"], parse_path_id(screenshot_id, "Screenshot"))
    if stream is None:
        raise NotFoundError("Screenshot not found")
    return stream


def is_terminal(run: dict) -> bool:
    return run["status"] not in (RunStatus.QUEUED.value, RunStatus.RUNNING.value)


async def logs_after(run_id: ObjectId, after_id: Optional[ObjectId], limit: int) -> list[dict]:
    return await run_log_repository.list_after(run_id, after_id, limit)
