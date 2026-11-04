import base64
import hashlib
import hmac
from urllib.parse import urlencode

from app.config import Settings, get_settings
from app.main import app
from app.routes.twilio_webhook import get_twilio_inbound_workflow


class FakeWorkflow:
    def __init__(self):
        self.inbound = []
        self.statuses = []

    async def ingest_message(self, **kwargs):
        self.inbound.append(kwargs)
        return True

    def apply_delivery_status(self, message_id, status):
        self.statuses.append((message_id, status))


def signature(url, params, token):
    value = url + "".join(key + params[key] for key in sorted(params))
    digest = hmac.new(token.encode(), value.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def twilio_settings(settings_values):
    return Settings(
        _env_file=None,
        **{
            **settings_values,
            "whatsapp_provider": "twilio",
            "public_base_url": "https://hawlak-tunnel.example",
            "twilio_account_sid": "AC" + "1" * 32,
            "twilio_auth_token": "twilio-test-auth-token-long-enough",
            "twilio_whatsapp_from": "+14155238886",
        },
    )


def test_twilio_webhook_accepts_signed_image(client, settings_values):
    settings = twilio_settings(settings_values)
    workflow = FakeWorkflow()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_twilio_inbound_workflow] = lambda: workflow
    params = {
        "MessageSid": "SM-inbound",
        "From": "whatsapp:+966500000000",
        "Body": "",
        "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/media/ME1",
        "MediaContentType0": "image/jpeg",
    }
    try:
        response = client.post(
            "/webhooks/twilio",
            content=urlencode(params),
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "x-twilio-signature": signature(
                    "https://hawlak-tunnel.example/webhooks/twilio",
                    params,
                    settings.twilio_auth_token.get_secret_value(),
                ),
            },
        )
    finally:
        app.dependency_overrides.pop(get_twilio_inbound_workflow, None)

    assert response.status_code == 204
    assert workflow.inbound == [
        {
            "wa_message_id": "SM-inbound",
            "sender": "+966500000000",
            "message_type": "image",
            "media_id": "https://api.twilio.com/media/ME1",
            "mime_type": "image/jpeg",
            "text": "",
            "button_payload": None,
        }
    ]


def test_twilio_webhook_rejects_invalid_signature(client, settings_values):
    settings = twilio_settings(settings_values)
    app.dependency_overrides[get_settings] = lambda: settings

    response = client.post(
        "/webhooks/twilio",
        content="MessageSid=SM1",
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "x-twilio-signature": "invalid",
        },
    )

    assert response.status_code == 401


def test_twilio_status_callback_updates_delivery(client, settings_values):
    settings = twilio_settings(settings_values)
    workflow = FakeWorkflow()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_twilio_inbound_workflow] = lambda: workflow
    params = {"MessageSid": "SM-outbound", "MessageStatus": "delivered"}
    try:
        response = client.post(
            "/webhooks/twilio",
            content=urlencode(params),
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "x-twilio-signature": signature(
                    "https://hawlak-tunnel.example/webhooks/twilio",
                    params,
                    settings.twilio_auth_token.get_secret_value(),
                ),
            },
        )
    finally:
        app.dependency_overrides.pop(get_twilio_inbound_workflow, None)

    assert response.status_code == 204
    assert workflow.statuses == [("SM-outbound", "delivered")]
