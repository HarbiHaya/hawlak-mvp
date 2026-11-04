import logging

from fastapi.testclient import TestClient

from app.config import get_settings
from app.webhook_main import app


def test_public_webhook_app_exposes_verification_but_not_internal_routes(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            verified = client.get(
                "/webhooks/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": settings.whatsapp_verify_token,
                    "hub.challenge": "12345",
                },
            )
            internal = client.post("/internal/demo/send-text")
    finally:
        app.dependency_overrides.clear()

    assert verified.status_code == 200
    assert verified.text == "12345"
    assert internal.status_code == 404


def test_public_webhook_access_log_does_not_include_query_token(settings, caplog):
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with caplog.at_level(logging.INFO, logger="app.webhook_main"), TestClient(app) as client:
            response = client.get(
                "/webhooks/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": settings.whatsapp_verify_token,
                    "hub.challenge": "12345",
                },
            )
    finally:
        app.dependency_overrides.clear()

    webhook_log = "\n".join(
        record.getMessage() for record in caplog.records if record.name == "app.webhook_main"
    )
    assert response.status_code == 200
    assert "method=GET path=/webhooks/whatsapp status=200" in webhook_log
    assert settings.whatsapp_verify_token not in webhook_log
