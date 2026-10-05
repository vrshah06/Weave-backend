from tests.conftest import CSV_HEADER, clinic_today, future_date, upload_csv, us

DAY = future_date(2)


def test_latest_is_404_without_runs(client):
    response = client.get("/api/v1/runs/latest")
    assert response.status_code == 404 and response.json()["error"]["message"] == "No runs found"


def test_create_run_validations(client):
    assert client.post("/api/v1/runs", json={"appointmentDate": DAY.isoformat(), "mode": "DRY_RUN"}).status_code == 400
    upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,\n')

    past = client.post("/api/v1/runs", json={"appointmentDate": "2020-01-01", "mode": "DRY_RUN"})
    assert past.status_code == 400 and "past date" in past.json()["error"]["message"]
    assert client.post("/api/v1/runs", json={"appointmentDate": DAY.isoformat(), "mode": "LIVE"}).status_code == 422

    run = client.post("/api/v1/runs", json={"appointmentDate": DAY.isoformat(), "mode": "DRY_RUN"})
    assert run.status_code == 202 and run.json()["status"] == "QUEUED"
    duplicate = client.post("/api/v1/runs", json={"appointmentDate": DAY.isoformat(), "mode": "SEND"})
    assert duplicate.status_code == 409 and duplicate.json()["error"]["details"]["runId"] == run.json()["id"]


def test_today_is_allowed_and_queued_runs_can_be_cancelled(client):
    today = clinic_today()
    upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(today)},11:59 PM,\n')
    run = client.post("/api/v1/runs", json={"appointmentDate": today.isoformat(), "mode": "DRY_RUN"}).json()
    assert client.get("/api/v1/runs/latest").json()["id"] == run["id"]

    stopped = client.post(f"/api/v1/runs/{run['id']}/stop").json()
    assert stopped["status"] == "CANCELLED"
    assert client.post(f"/api/v1/runs/{run['id']}/stop").status_code == 409
    assert client.get("/api/v1/runs", params={"status": "CANCELLED"}).json()["total"] == 1
