import logging

import httpx

from app.main import app
from app.routes.demo import get_whatsapp_client


def test_internal_route_rejects_a_missing_bearer_token(client):
    response = client.post("/internal/demo/send-text")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_internal_route_rejects_a_malformed_authorization_header(client):
    response = client.post(
        "/internal/demo/send-text",
        headers={"Authorization": "Basic not-a-bearer-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_internal_route_rejects_a_wrong_bearer_token(client):
    response = client.post(
        "/internal/demo/send-text",
        headers={"Authorization": "Bearer wrong-token-that-is-long-enough"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_internal_route_accepts_the_configured_token(client, fake_meta, internal_auth_headers):
    whatsapp, _ = fake_meta(httpx.Response(200, json={"messages": [{"id": "wamid.DEMO"}]}))
    app.dependency_overrides[get_whatsapp_client] = lambda: whatsapp

    response = client.post("/internal/demo/send-text", headers=internal_auth_headers)

    assert response.status_code == 202


def test_internal_authentication_never_logs_token_text(client, settings, caplog):
    configured_token = settings.internal_api_token.get_secret_value()
    wrong_token = "wrong-token-that-must-not-be-logged"

    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/internal/demo/send-text",
            headers={"Authorization": f"Bearer {wrong_token}"},
        )

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert response.status_code == 401
    assert configured_token not in logged
    assert wrong_token not in logged


def test_cors_allows_only_the_configured_local_dashboard_origin(client, settings):
    response = client.options(
        "/internal/demo/send-text",
        headers={
            "Origin": settings.dashboard_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type, Idempotency-Key",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == settings.dashboard_origin
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers


def test_cors_rejects_every_other_origin(client):
    response = client.options(
        "/internal/demo/send-text",
        headers={
            "Origin": "http://localhost:4173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
