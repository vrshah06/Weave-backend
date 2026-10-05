from models.enums import AppointmentStatus
from repositories import appointment_repository
from tests.conftest import CSV_HEADER, future_date, run_async, upload_csv, us

DAY = future_date(2)


def rows_by_status(body):
    result = {}
    for row in body["rows"]:
        result.setdefault(row["status"], []).append(row)
    return result


def test_import_creates_patients_and_appointments(client):
    response = upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,Dr A\nBad Row,123,{us(DAY)},9:00 AM,\n')
    assert response.status_code == 201
    body = response.json()
    assert body["counts"] == {"rows": 2, "created": 1, "updated": 0, "reactivated": 0, "unchanged": 0, "cancelled": 0, "invalid": 1}
    created = rows_by_status(body)["CREATED"][0]
    assert created["patientName"] == "Jane Doe" and created["phone"] == "+17726379314" and created["appointmentTime"] == "09:00"
    assert rows_by_status(body)["INVALID"][0]["row"] == 3


def test_same_person_in_different_formats_is_one_appointment(client):
    upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,\n')
    body = upload_csv(client, CSV_HEADER + f"JANE DOE,(772) 637 9314,{DAY.isoformat()},09:00,\n").json()
    assert body["counts"]["unchanged"] == 1 and body["counts"]["created"] == 0


def test_shared_phone_different_names_are_separate_appointments(client):
    body = upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,\n"Doe, Tim",772-637-9314,{us(DAY)},9:00 AM,\n').json()
    assert body["counts"]["created"] == 2


def test_duplicate_rows_within_a_file_are_reported(client):
    body = upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,\nJane Doe,7726379314,{us(DAY)},9:00 AM,\n').json()
    assert body["counts"]["created"] == 1 and rows_by_status(body)["DUPLICATE_IN_FILE"][0]["row"] == 3


def test_reimport_syncs_the_date(client):
    first = upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,Dr A\n"Roe, Rick",772-555-1234,{us(DAY)},10:00 AM,\n').json()
    rick_id = rows_by_status(first)["CREATED"][1]["appointmentId"]

    second = upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,Dr B\n').json()
    assert second["counts"]["updated"] == 1 and second["counts"]["cancelled"] == 1
    assert second["cancelled"][0]["appointmentId"] == rick_id

    third = upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,Dr B\n"Roe, Rick",772-555-1234,{us(DAY)},10:00 AM,\n').json()
    assert third["counts"]["reactivated"] == 1 and third["counts"]["unchanged"] == 1


def test_sync_never_cancels_sent_appointments_or_other_dates(client):
    other_day = future_date(3)
    first = upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,\n"Roe, Rick",772-555-1234,{us(other_day)},10:00 AM,\n').json()
    jane_id = rows_by_status(first)["CREATED"][0]["appointmentId"]

    from bson import ObjectId
    run_async(client, appointment_repository.update_fields, ObjectId(jane_id), {"status": AppointmentStatus.SENT.value})
    body = upload_csv(client, CSV_HEADER + f'"Poe, Ann",772-555-9999,{us(DAY)},11:00 AM,\n').json()
    assert body["counts"]["cancelled"] == 0
    assert client.get("/api/v1/appointments", params={"date": other_day.isoformat()}).json()["appointments"][0]["status"] == "PENDING"


def test_unusable_files_are_rejected(client):
    assert upload_csv(client, "").status_code == 400
    assert upload_csv(client, "foo,bar\n1,2\n").json()["error"]["message"].startswith("CSV header is missing")
    response = upload_csv(client, CSV_HEADER + f"Bad,123,{us(DAY)},9:00 AM,\n")
    assert response.status_code == 400 and response.json()["error"]["details"][0]["row"] == 2


def test_import_history(client):
    created = upload_csv(client, CSV_HEADER + f'"Doe, Jane",772-637-9314,{us(DAY)},9:00 AM,\n').json()
    listing = client.get("/api/v1/imports").json()
    assert listing["total"] == 1 and "rows" not in listing["items"][0]
    assert client.get(f"/api/v1/imports/{created['id']}").json()["rows"][0]["status"] == "CREATED"
    assert client.get("/api/v1/imports/not-an-id").status_code == 404
