def test_defaults_then_update(client):
    defaults = client.get("/api/v1/settings").json()
    assert defaults["timeZone"] == "America/New_York" and "{appointment_date}" in defaults["messageTemplate"]

    payload = {"businessName": "Sunrise Clinic", "messageTemplate": "Hi {first_name}, see you {appointment_date} at {appointment_time}.", "timeZone": "America/Chicago"}
    assert client.put("/api/v1/settings", json=payload).json() == payload
    assert client.get("/api/v1/settings/message-preview").json()["message"] == "Hi Jane, see you 10/02/2026 at 9:00 AM."


def test_invalid_templates_and_time_zones_are_rejected(client):
    base = {"businessName": "X", "messageTemplate": "ok", "timeZone": "America/New_York"}
    for template in ("Hi {name}", "Hi {first_name", "At {appointment_time:>10}"):
        response = client.put("/api/v1/settings", json={**base, "messageTemplate": template})
        assert response.status_code == 400, template
    assert client.put("/api/v1/settings", json={**base, "timeZone": "Mars/Olympus"}).status_code == 400
