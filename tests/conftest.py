import os
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TEST_MONGODB_BASE_URI = os.getenv("TEST_MONGODB_BASE_URI", "mongodb://127.0.0.1:27018")
API_KEY = "test-api-key"

os.environ["MONGODB_URI"] = f"{TEST_MONGODB_BASE_URI}/weave_test_{uuid.uuid4().hex[:8]}"
os.environ["API_KEY"] = API_KEY
os.environ["SENDING_ENABLED"] = "false"
os.environ["TIME_ZONE"] = "America/New_York"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import database  # noqa: E402

CSV_HEADER = "patient_name,phone,appointment_date,appointment_time,provider\n"


def clinic_today() -> date:
    return datetime.now(ZoneInfo("America/New_York")).date()


def future_date(days: int = 1) -> date:
    return clinic_today() + timedelta(days=days)


def us(d: date) -> str:
    return d.strftime("%m/%d/%Y")


async def _reset_database() -> None:
    db = database.get_db()
    await db.client.drop_database(db.name)
    await database.ensure_indexes()


@pytest.fixture
def client():
    from app import app
    with TestClient(app, headers={"X-API-Key": API_KEY}) as test_client:
        test_client.portal.call(_reset_database)
        yield test_client


def upload_csv(client: TestClient, text: str, name: str = "appointments.csv"):
    return client.post("/api/v1/imports", files={"file": (name, text, "text/csv")})


def run_async(client: TestClient, func, *args):
    return client.portal.call(func, *args)
