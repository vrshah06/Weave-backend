from typing import Optional

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from core.config import config

DEFAULT_DATABASE_NAME = "weave_automation"

_client: Optional[AsyncMongoClient] = None


def connect(uri: Optional[str] = None) -> None:
    global _client
    if _client is None:
        _client = AsyncMongoClient(uri or config.mongodb_uri, tz_aware=True)


def get_db() -> AsyncDatabase:
    if _client is None:
        raise RuntimeError("Database is not connected; call core.database.connect() first.")
    return _client.get_default_database(default=DEFAULT_DATABASE_NAME)


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
    _client = None


async def ping() -> bool:
    try:
        await get_db().command("ping")
        return True
    except Exception:
        return False


async def ensure_indexes() -> None:
    db = get_db()
    await db.patients.create_index([("name_key", ASCENDING), ("phone", ASCENDING)], unique=True, name="uniq_patient_name_phone")
    await db.appointments.create_index(
        [("patient_id", ASCENDING), ("appointment_date", ASCENDING), ("appointment_time", ASCENDING)],
        unique=True, name="uniq_appointment_slot",
    )
    await db.appointments.create_index([("appointment_date", ASCENDING), ("status", ASCENDING)], name="appointments_by_date_status")
    await db.imports.create_index([("created_at", DESCENDING)], name="imports_by_created")
    await db.runs.create_index([("status", ASCENDING), ("queued_at", ASCENDING)], name="runs_by_status_queued")
    await db.runs.create_index([("queued_at", DESCENDING)], name="runs_by_queued_desc")
    await db.run_items.create_index([("run_id", ASCENDING), ("appointment_id", ASCENDING)], unique=True, name="uniq_run_item")
    await db.run_items.create_index([("appointment_id", ASCENDING), ("started_at", DESCENDING)], name="run_items_by_appointment")
    await db.run_logs.create_index([("run_id", ASCENDING), ("_id", ASCENDING)], name="run_logs_by_run")
