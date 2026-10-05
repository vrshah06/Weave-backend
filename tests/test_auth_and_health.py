from tests.conftest import API_KEY


def test_requests_without_a_valid_api_key_are_rejected(client):
    for headers in ({"X-API-Key": ""}, {"X-API-Key": "wrong"}):
        response = client.get("/api/v1/settings", headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


def test_events_endpoint_accepts_query_api_key(client):
    response = client.get("/api/v1/runs/000000000000000000000000/events", headers={"X-API-Key": ""}, params={"apiKey": API_KEY})
    assert response.status_code == 404


def test_health_needs_no_key_and_reports_worker_offline(client):
    response = client.get("/api/v1/health", headers={"X-API-Key": ""})
    assert response.status_code == 200
    assert response.json()["database"] == "up"
    assert response.json()["worker"] == "offline"


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"
