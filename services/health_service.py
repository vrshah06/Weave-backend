from core import database
from repositories import worker_lock_repository
from utils.clock import utc_now


async def check() -> dict:
    database_up = await database.ping()
    lock = await worker_lock_repository.find() if database_up else None
    if not database_up:
        worker = "unknown"
    elif lock and lock["expires_at"] > utc_now():
        worker = "online"
    else:
        worker = "offline"
    return {
        "status": "ok" if database_up and worker == "online" else "degraded",
        "database": "up" if database_up else "down",
        "worker": worker,
        "worker_heartbeat_at": lock.get("heartbeat_at") if lock else None,
        "checked_at": utc_now(),
    }
