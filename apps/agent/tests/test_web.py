from fastapi.testclient import TestClient

from hawlak_agent.control import MockCallDispatcher
from hawlak_agent.settings import AgentSettings
from hawlak_agent.web import create_app


def settings() -> AgentSettings:
    return AgentSettings.from_mapping(
        {
            "HAWLAK_AGENT_MODE": "mock",
            "HAWLAK_API_BASE_URL": "http://api:3000",
            "HAWLAK_INTERNAL_API_TOKEN": "internal-token",
            "HAWLAK_CONTROL_TOKEN": "control-token",
        }
    )


def test_health_is_public_and_does_not_expose_configuration() -> None:
    client = TestClient(create_app(settings(), MockCallDispatcher()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "mock"}


def test_calls_requires_bearer_and_idempotency_key() -> None:
    client = TestClient(create_app(settings(), MockCallDispatcher()))
    body = {
        "callPlanId": "plan-synthetic-001",
        "caseId": "case-synthetic-001",
        "scheduledAt": "2026-11-12T09:30:00Z",
    }

    assert client.post("/calls", json=body).status_code == 401
    assert (
        client.post(
            "/calls",
            json=body,
            headers={"Authorization": "Bearer control-token"},
        ).status_code
        == 400
    )

    accepted = client.post(
        "/calls",
        json=body,
        headers={
            "Authorization": "Bearer control-token",
            "Idempotency-Key": "idem-synthetic-001",
        },
    )

    assert accepted.status_code == 202
    assert accepted.json()["status"] == "accepted"
