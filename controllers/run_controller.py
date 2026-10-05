import asyncio
from typing import Optional

from bson import ObjectId
from fastapi import Request
from fastapi.responses import StreamingResponse

from controllers.presenters import present_run, present_run_item, present_run_log
from models.common import Page
from models.enums import RunStatus
from models.run_models import RunCreateRequest, RunItemResponse, RunLogResponse, RunResponse
from services import run_service

EVENT_POLL_SECONDS = 1.0
KEEPALIVE_SECONDS = 15.0


async def create_run(request: RunCreateRequest) -> RunResponse:
    return present_run(await run_service.create_run(request.appointment_date, request.mode))


async def list_runs(status: Optional[RunStatus], limit: int, offset: int) -> Page[RunResponse]:
    runs, total = await run_service.list_page(status, limit, offset)
    return Page(items=[present_run(r) for r in runs], total=total, limit=limit, offset=offset)


async def get_latest_run() -> RunResponse:
    return present_run(await run_service.get_latest())


async def get_run(run_id: str) -> RunResponse:
    return present_run(await run_service.get(run_id))


async def stop_run(run_id: str) -> RunResponse:
    return present_run(await run_service.stop(run_id))


async def list_run_items(run_id: str) -> list[RunItemResponse]:
    return [present_run_item(i) for i in await run_service.list_items(run_id)]


async def list_run_logs(run_id: str, after: Optional[str], limit: int) -> list[RunLogResponse]:
    return [present_run_log(log) for log in await run_service.list_logs(run_id, after, limit)]


async def get_screenshot(run_id: str, screenshot_id: str) -> StreamingResponse:
    stream = await run_service.open_screenshot(run_id, screenshot_id)
    return StreamingResponse(stream, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


def _sse(event: str, data: str, event_id: Optional[str] = None) -> str:
    lines = [f"event: {event}"]
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"data: {data}")
    return "\n".join(lines) + "\n\n"


async def stream_run_events(request: Request, run_id: str, last_event_id: Optional[str]) -> StreamingResponse:
    run = await run_service.get(run_id)
    after = ObjectId(last_event_id) if last_event_id and ObjectId.is_valid(last_event_id) else None

    async def events():
        nonlocal after
        last_snapshot = None
        idle_seconds = 0.0
        while not await request.is_disconnected():
            logs = await run_service.logs_after(run["_id"], after, 200)
            for log in logs:
                after = log["_id"]
                yield _sse("log", present_run_log(log).model_dump_json(by_alias=True), str(log["_id"]))

            current = await run_service.get(run_id)
            snapshot = present_run(current).model_dump_json(by_alias=True)
            if snapshot != last_snapshot:
                last_snapshot = snapshot
                yield _sse("run", snapshot)
            if run_service.is_terminal(current) and not logs:
                yield _sse("end", snapshot)
                return

            if logs:
                idle_seconds = 0.0
            else:
                idle_seconds += EVENT_POLL_SECONDS
                if idle_seconds >= KEEPALIVE_SECONDS:
                    idle_seconds = 0.0
                    yield ": keep-alive\n\n"
            await asyncio.sleep(EVENT_POLL_SECONDS)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
