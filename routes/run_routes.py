from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request

from controllers import run_controller
from core.security import require_api_key, require_api_key_header_or_query
from models.common import Page
from models.enums import RunStatus
from models.run_models import RunCreateRequest, RunItemResponse, RunLogResponse, RunResponse

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunResponse, status_code=202, dependencies=[Depends(require_api_key)],
             summary="Queue a run for every PENDING, non-excluded appointment on a date")
async def create_run(request: RunCreateRequest):
    return await run_controller.create_run(request)


@router.get("", response_model=Page[RunResponse], dependencies=[Depends(require_api_key)])
async def list_runs(status: Optional[RunStatus] = None, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await run_controller.list_runs(status, limit, offset)


@router.get("/latest", response_model=RunResponse, dependencies=[Depends(require_api_key)], summary="Most recent run (404 if there are none)")
async def get_latest_run():
    return await run_controller.get_latest_run()


@router.get("/{run_id}", response_model=RunResponse, dependencies=[Depends(require_api_key)])
async def get_run(run_id: str):
    return await run_controller.get_run(run_id)


@router.post("/{run_id}/stop", response_model=RunResponse, dependencies=[Depends(require_api_key)],
             summary="Cancel a queued run, or stop a running one after the current patient")
async def stop_run(run_id: str):
    return await run_controller.stop_run(run_id)


@router.get("/{run_id}/items", response_model=list[RunItemResponse], dependencies=[Depends(require_api_key)])
async def list_run_items(run_id: str):
    return await run_controller.list_run_items(run_id)


@router.get("/{run_id}/logs", response_model=list[RunLogResponse], dependencies=[Depends(require_api_key)])
async def list_run_logs(run_id: str, after: Optional[str] = None, limit: int = Query(500, ge=1, le=1000)):
    return await run_controller.list_run_logs(run_id, after, limit)


@router.get("/{run_id}/events", dependencies=[Depends(require_api_key_header_or_query)],
            summary="Server-Sent Events: 'log', 'run' and a final 'end' event")
async def stream_run_events(request: Request, run_id: str, last_event_id: Optional[str] = Header(None)):
    return await run_controller.stream_run_events(request, run_id, last_event_id)


@router.get("/{run_id}/screenshots/{screenshot_id}", dependencies=[Depends(require_api_key_header_or_query)],
            summary="Failure screenshot (PNG)")
async def get_screenshot(run_id: str, screenshot_id: str):
    return await run_controller.get_screenshot(run_id, screenshot_id)
