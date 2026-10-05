from dataclasses import replace
from datetime import timedelta

from bson import ObjectId

from core.config import config
from models.enums import AppointmentStatus, RunItemStatus, RunMode, RunStatus
from repositories import appointment_repository, run_item_repository, run_repository, worker_lock_repository
from tests.conftest import API_KEY, CSV_HEADER, future_date, run_async, upload_csv, us
from tests.fakes import FAKE_PNG, FakeWeaveDriver
from worker.worker import Worker

DAY = future_date(2)
JANE, RICK, ANN = "+17726379314", "+17725551234", "+17725559999"


def import_three(client):
    upload_csv(client, CSV_HEADER + (
        f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,Dr A\n'
        f'"Roe, Rick",772-555-1234,{us(DAY)},10:00 AM,\n'
        f'"Poe, Ann",772-555-9999,{us(DAY)},11:00 AM,\n'
    ))


def statuses(client):
    return {a["patientName"]: a["status"] for a in client.get("/api/v1/appointments", params={"date": DAY.isoformat()}).json()["appointments"]}


def start_run(client, mode):
    response = client.post("/api/v1/runs", json={"appointmentDate": DAY.isoformat(), "mode": mode})
    assert response.status_code == 202, response.json()
    return response.json()["id"]


def work(client, driver, sending_enabled=False, max_errors=3):
    worker = Worker(lambda: driver, replace(config, sending_enabled=sending_enabled, worker_max_consecutive_errors=max_errors))
    return run_async(client, worker.run_next)


def test_dry_run_verifies_without_changing_appointments(client):
    import_three(client)
    run_id = start_run(client, "DRY_RUN")
    driver = FakeWeaveDriver()
    assert work(client, driver) is True

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "COMPLETED" and run["counts"]["dryRunVerified"] == 3 and run["counts"]["remaining"] == 0
    assert set(statuses(client).values()) == {"PENDING"}
    assert driver.sent == [] and driver.discarded == 3 and driver.closed
    assert "9:00 AM with MD Primary Care Inc." in driver.prepared[0][1]

    events = [log["event"] for log in client.get(f"/api/v1/runs/{run_id}/logs").json()]
    assert events[0] == "run.started" and events[-1] == "run.finished" and events.count("patient.finished") == 3

    send_run = start_run(client, "SEND")
    work(client, FakeWeaveDriver(), sending_enabled=True)
    assert client.get(f"/api/v1/runs/{send_run}").json()["counts"]["sent"] == 3
    assert set(statuses(client).values()) == {"SENT"}


def test_send_is_refused_when_sending_is_disabled(client):
    import_three(client)
    run_id = start_run(client, "SEND")
    driver = FakeWeaveDriver()
    work(client, driver, sending_enabled=False)
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "FAILED" and "SENDING_ENABLED" in run["error"]
    assert driver.prepared == [] and set(statuses(client).values()) == {"PENDING"}


def test_send_outcomes_map_to_appointment_statuses(client):
    import_three(client)
    run_id = start_run(client, "SEND")
    work(client, FakeWeaveDriver({RICK: "unconfirmed", ANN: "not_verified"}), sending_enabled=True)

    assert statuses(client) == {"Jane Doe": "SENT", "Rick Roe": "NEEDS_REVIEW", "Ann Poe": "SKIPPED"}
    counts = client.get(f"/api/v1/runs/{run_id}").json()["counts"]
    assert (counts["sent"], counts["needsReview"], counts["skipped"]) == (1, 1, 1)

    items = {i["patientName"]: i for i in client.get(f"/api/v1/runs/{run_id}/items").json()}
    assert items["Jane Doe"]["screenshotUrl"] is None
    screenshot = client.get(items["Ann Poe"]["screenshotUrl"], headers={"X-API-Key": ""}, params={"apiKey": API_KEY})
    assert screenshot.status_code == 200 and screenshot.content == FAKE_PNG and screenshot.headers["content-type"] == "image/png"
    assert client.get(f"/api/v1/runs/{ObjectId()}/screenshots/{items['Ann Poe']['screenshotUrl'].rsplit('/', 1)[1]}").status_code == 404


def test_not_delivered_and_crashes(client):
    import_three(client)
    start_run(client, "SEND")
    driver = FakeWeaveDriver({JANE: "not_delivered", RICK: "send_crash", ANN: "crash"})
    work(client, driver, sending_enabled=True)
    assert statuses(client) == {"Jane Doe": "FAILED", "Rick Roe": "NEEDS_REVIEW", "Ann Poe": "FAILED"}
    assert driver.sent == [JANE] and driver.resets == 1


def test_dry_run_failures_leave_appointments_pending(client):
    import_three(client)
    run_id = start_run(client, "DRY_RUN")
    work(client, FakeWeaveDriver({JANE: "not_verified", RICK: "ui_error"}))
    assert set(statuses(client).values()) == {"PENDING"}
    counts = client.get(f"/api/v1/runs/{run_id}").json()["counts"]
    assert (counts["skipped"], counts["failed"], counts["dryRunVerified"]) == (1, 1, 1)


def test_excluded_and_cancelled_appointments_are_not_messaged(client):
    import_three(client)
    jane_id = next(a["id"] for a in client.get("/api/v1/appointments", params={"date": DAY.isoformat()}).json()["appointments"] if a["patientName"] == "Jane Doe")
    client.post("/api/v1/appointments/exclusions", json={"appointmentIds": [jane_id], "excluded": True})
    upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,Dr A\n"Roe, Rick",772-555-1234,{us(DAY)},10:00 AM,\n')
    start_run(client, "SEND")
    driver = FakeWeaveDriver()
    work(client, driver, sending_enabled=True)
    assert driver.sent == [RICK]
    assert statuses(client) == {"Jane Doe": "PENDING", "Rick Roe": "SENT", "Ann Poe": "CANCELLED"}


def test_stop_finishes_current_patient_then_stops(client):
    import_three(client)
    run_id = start_run(client, "SEND")

    async def stop_after_first(recipient):
        if recipient.phone == JANE:
            await run_repository.request_stop_if_running(ObjectId(run_id))

    work(client, FakeWeaveDriver(before_prepare=stop_after_first), sending_enabled=True)
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "STOPPED" and run["counts"]["processed"] == 1
    assert statuses(client) == {"Jane Doe": "SENT", "Rick Roe": "PENDING", "Ann Poe": "PENDING"}


def test_repeated_browser_errors_abort_the_run(client):
    import_three(client)
    run_id = start_run(client, "SEND")
    work(client, FakeWeaveDriver({JANE: "ui_error", RICK: "ui_error", ANN: "ui_error"}), sending_enabled=True, max_errors=2)
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "FAILED" and "2 consecutive" in run["error"]
    assert statuses(client)["Ann Poe"] == "PENDING"


def test_login_failure_fails_the_run(client):
    import_three(client)
    run_id = start_run(client, "DRY_RUN")
    driver = FakeWeaveDriver(fail_login=True)
    work(client, driver)
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "FAILED" and "Weave login failed" in run["error"] and driver.closed


def test_appointment_changed_mid_run_is_skipped(client):
    import_three(client)
    start_run(client, "SEND")
    rows = client.get("/api/v1/appointments", params={"date": DAY.isoformat()}).json()["appointments"]
    ann_id = next(a["id"] for a in rows if a["patientName"] == "Ann Poe")

    async def exclude_ann(recipient):
        if recipient.phone == JANE:
            await appointment_repository.set_excluded([ObjectId(ann_id)], True)

    driver = FakeWeaveDriver(before_prepare=exclude_ann)
    work(client, driver, sending_enabled=True)
    assert ANN not in driver.sent and statuses(client)["Ann Poe"] == "PENDING"


def test_recovery_marks_orphaned_work(client):
    import_three(client)
    run_id = start_run(client, "SEND")
    jane_id = next(a["id"] for a in client.get("/api/v1/appointments", params={"date": DAY.isoformat()}).json()["appointments"] if a["patientName"] == "Jane Doe")

    async def simulate_crash_mid_send():
        run = await run_repository.claim_next_queued("dead-worker")
        appointment = await appointment_repository.find_by_id(ObjectId(jane_id))
        await run_item_repository.start(run["_id"], appointment["_id"], appointment["patient_id"])
        await appointment_repository.claim_for_sending(appointment["_id"], run["_id"])
    run_async(client, simulate_crash_mid_send)

    worker = Worker(lambda: FakeWeaveDriver(), config)
    assert run_async(client, worker.hold_lock) is True
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "INTERRUPTED"
    assert statuses(client)["Jane Doe"] == "NEEDS_REVIEW"
    assert client.get(f"/api/v1/runs/{run_id}/items").json()[0]["status"] == RunItemStatus.NEEDS_REVIEW.value


def test_only_one_worker_holds_the_browser_lock(client):
    first, second = Worker(lambda: FakeWeaveDriver(), config), Worker(lambda: FakeWeaveDriver(), config)
    assert run_async(client, first.hold_lock) is True
    assert run_async(client, second.hold_lock) is False
    assert client.get("/api/v1/health").json()["worker"] == "online"
    run_async(client, worker_lock_repository.release, first.worker_id)
    assert run_async(client, second.hold_lock) is True


def test_queued_runs_are_claimed_once_in_order(client):
    import_three(client)
    first = start_run(client, "DRY_RUN")
    claimed = run_async(client, run_repository.claim_next_queued, "w1")
    assert str(claimed["_id"]) == first
    assert run_async(client, run_repository.claim_next_queued, "w2") is None


def test_event_stream_replays_logs_and_ends(client):
    import_three(client)
    run_id = start_run(client, "DRY_RUN")
    work(client, FakeWeaveDriver())
    with client.stream("GET", f"/api/v1/runs/{run_id}/events") as response:
        body = "".join(response.iter_text())
    assert body.count("event: log") == len(client.get(f"/api/v1/runs/{run_id}/logs").json())
    assert "event: run" in body and body.rstrip().split("\n")[-2] == "event: end"

    logs = client.get(f"/api/v1/runs/{run_id}/logs").json()
    with client.stream("GET", f"/api/v1/runs/{run_id}/events", headers={"Last-Event-ID": logs[-2]["id"]}) as response:
        resumed = "".join(response.iter_text())
    assert resumed.count("event: log") == 1


def test_run_status_enum_values_are_stable():
    assert {s.value for s in RunStatus} >= {"QUEUED", "RUNNING", "COMPLETED", "STOPPED", "CANCELLED", "FAILED", "INTERRUPTED"}
    assert RunMode("DRY_RUN") is RunMode.DRY_RUN and AppointmentStatus("SENDING")
    assert timedelta(seconds=config.worker_lock_ttl_seconds) > timedelta(seconds=config.worker_poll_interval_seconds)
