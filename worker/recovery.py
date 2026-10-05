import logging

from repositories import appointment_repository, run_item_repository, run_repository
from worker.run_logger import RunLogger

logger = logging.getLogger("weave.worker")

INTERRUPTED_RUN_REASON = "Worker stopped unexpectedly during this run"
STUCK_SENDING_REASON = "Worker stopped while sending; check Weave to see whether the message went out"


async def recover_interrupted_work() -> None:
    """Called once the worker holds the browser lock, so any RUNNING run is orphaned."""
    run_ids = await run_repository.interrupt_running(INTERRUPTED_RUN_REASON)
    stuck_ids = await appointment_repository.release_stuck_sending(STUCK_SENDING_REASON)
    if run_ids:
        await run_item_repository.resolve_in_progress(run_ids, stuck_ids, INTERRUPTED_RUN_REASON)
        for run_id in run_ids:
            await RunLogger(run_id).error("run.interrupted", INTERRUPTED_RUN_REASON)
    if run_ids or stuck_ids:
        logger.warning("Recovered %d interrupted run(s) and %d appointment(s) stuck in SENDING", len(run_ids), len(stuck_ids))
