import asyncio
import logging
import signal
import socket
import uuid
from typing import Callable

from automation.driver import MessagingDriver
from core import database
from core.config import AppConfig, config
from repositories import run_repository, worker_lock_repository
from worker.recovery import recover_interrupted_work
from worker.run_executor import RunExecutor

logger = logging.getLogger("weave.worker")


class Worker:
    def __init__(self, driver_factory: Callable[[], MessagingDriver], settings: AppConfig = config):
        self.driver_factory = driver_factory
        self.settings = settings
        self.worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self.shutdown = asyncio.Event()
        self.recovered = False

    async def run_forever(self) -> None:
        database.connect()
        await database.ensure_indexes()
        self._install_signal_handlers()
        logger.info("Worker %s started (sending_enabled=%s)", self.worker_id, self.settings.sending_enabled)
        try:
            while not self.shutdown.is_set():
                if not await self.hold_lock():
                    logger.info("Another worker holds the browser lock; waiting")
                    await self._wait(self.settings.worker_poll_interval_seconds)
                    continue
                if not await self.run_next():
                    await self._wait(self.settings.worker_poll_interval_seconds)
        finally:
            await worker_lock_repository.release(self.worker_id)
            await database.close()
            logger.info("Worker %s stopped", self.worker_id)

    async def hold_lock(self) -> bool:
        if not await worker_lock_repository.acquire(self.worker_id, self.settings.worker_lock_ttl_seconds):
            return False
        if not self.recovered:
            await recover_interrupted_work()
            self.recovered = True
        return True

    async def run_next(self) -> bool:
        run = await run_repository.claim_next_queued(self.worker_id)
        if run is None:
            return False
        logger.info("Claimed run %s (%s, %s)", run["_id"], run["mode"], run["appointment_date"])
        heartbeat = asyncio.create_task(self._heartbeat(run["_id"]))
        try:
            executor = RunExecutor(
                run,
                self.driver_factory(),
                sending_enabled=self.settings.sending_enabled,
                max_consecutive_errors=self.settings.worker_max_consecutive_errors,
                shutdown_requested=self.shutdown.is_set,
            )
            await executor.execute()
        finally:
            heartbeat.cancel()
        return True

    async def _heartbeat(self, run_id) -> None:
        while True:
            await asyncio.sleep(self.settings.worker_heartbeat_interval_seconds)
            try:
                await run_repository.heartbeat(run_id)
                if not await worker_lock_repository.acquire(self.worker_id, self.settings.worker_lock_ttl_seconds):
                    logger.error("Lost the browser lock during run %s", run_id)
            except Exception:
                logger.exception("Heartbeat failed for run %s", run_id)

    async def _wait(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self.shutdown.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._request_shutdown)
            except NotImplementedError:
                pass

    def _request_shutdown(self) -> None:
        logger.info("Shutdown requested; finishing the current patient first")
        self.shutdown.set()
