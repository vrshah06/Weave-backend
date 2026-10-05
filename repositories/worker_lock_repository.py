from datetime import timedelta
from typing import Optional

from pymongo.errors import DuplicateKeyError

from core.database import get_db
from utils.clock import utc_now

BROWSER_LOCK_ID = "weave-browser"


async def acquire(owner: str, ttl_seconds: int) -> bool:
    """Take or renew the single-browser lock; succeeds if free, expired, or already ours."""
    now = utc_now()
    try:
        await get_db().worker_locks.update_one(
            {"_id": BROWSER_LOCK_ID, "$or": [{"owner": owner}, {"expires_at": {"$lt": now}}]},
            {"$set": {"owner": owner, "heartbeat_at": now, "expires_at": now + timedelta(seconds=ttl_seconds)}},
            upsert=True,
        )
        return True
    except DuplicateKeyError:
        return False


async def release(owner: str) -> None:
    await get_db().worker_locks.delete_one({"_id": BROWSER_LOCK_ID, "owner": owner})


async def find() -> Optional[dict]:
    return await get_db().worker_locks.find_one({"_id": BROWSER_LOCK_ID})
