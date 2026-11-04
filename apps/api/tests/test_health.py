from datetime import datetime


def test_health_reports_the_service_is_up(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "hawlak-api"
    datetime.fromisoformat(body["time"])  # raises unless it is an ISO-8601 timestamp
