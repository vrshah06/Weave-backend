from bson import ObjectId

from models.enums import AppointmentStatus
from repositories import appointment_repository
from tests.conftest import CSV_HEADER, future_date, run_async, upload_csv, us

DAY = future_date(2)


def import_two(client):
    body = upload_csv(client, CSV_HEADER + f'"Roe, Rick",772-555-1234,{us(DAY)},10:00 AM,\n"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,\n').json()
    return [r["appointmentId"] for r in body["rows"]]


def test_list_by_date_is_time_ordered(client):
    import_two(client)
    body = client.get("/api/v1/appointments", params={"date": DAY.isoformat()}).json()
    assert [a["patientName"] for a in body["appointments"]] == ["Jane Doe", "Rick Roe"]
    assert client.get("/api/v1/appointments/dates").json()["dates"] == [DAY.isoformat()]


def test_bad_dates_and_ids_are_rejected(client):
    for value in ("10/02/2026", "2026-02-30", "2026-1-2"):
        response = client.get("/api/v1/appointments", params={"date": value})
        assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"
    assert client.get("/api/v1/appointments/xyz").status_code == 404
    assert client.post("/api/v1/appointments/requeue", json={"appointmentIds": ["xyz"]}).status_code == 400


def test_exclusions(client):
    jane, rick = import_two(client)
    response = client.post("/api/v1/appointments/exclusions", json={"appointmentIds": [jane, rick], "excluded": True}).json()
    assert response == {"matched": 2, "updated": 2}
    assert client.get(f"/api/v1/appointments/{jane}").json()["excluded"] is True


def test_requeue_and_mark_sent_only_touch_allowed_statuses(client):
    jane, rick = import_two(client)
    run_async(client, appointment_repository.update_fields, ObjectId(jane), {"status": AppointmentStatus.NEEDS_REVIEW.value})
    assert client.post("/api/v1/appointments/mark-sent", json={"appointmentIds": [jane, rick]}).json() == {"matched": 2, "updated": 1}
    sent = client.get(f"/api/v1/appointments/{jane}").json()
    assert sent["status"] == "SENT" and sent["sentAt"]

    run_async(client, appointment_repository.update_fields, ObjectId(rick), {"status": AppointmentStatus.FAILED.value})
    assert client.post("/api/v1/appointments/requeue", json={"appointmentIds": [jane, rick]}).json() == {"matched": 2, "updated": 1}
    assert client.get(f"/api/v1/appointments/{rick}").json()["status"] == "PENDING"


def test_patients(client):
    import_two(client)
    page = client.get("/api/v1/patients", params={"search": "doe"}).json()
    assert page["total"] == 1 and page["items"][0]["fullName"] == "Jane Doe"
    assert client.get("/api/v1/patients", params={"search": "555-1234"}).json()["items"][0]["fullName"] == "Rick Roe"
    assert client.get("/api/v1/patients", params={"search": ".*"}).json()["total"] == 0
    patient_id = page["items"][0]["id"]
    assert len(client.get(f"/api/v1/patients/{patient_id}/appointments").json()) == 1
