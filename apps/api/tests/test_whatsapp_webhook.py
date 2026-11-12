import json
import logging

import pytest

VERIFY_TOKEN = "test-verify-token-long-enough"
MEDICINE_PHOTO = {
    "id": "wamid.PHOTO1",
    "from": "966500001234",
    "type": "image",
    "image": {"id": "MEDIA-77", "mime_type": "image/jpeg"},
}


def webhook_body(value: dict) -> bytes:
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": value}]}]}
    return json.dumps(payload).encode()


def post_webhook(client, body: bytes, signature: str | None):
    headers = {"content-type": "application/json"}
    if signature is not None:
        headers["x-hub-signature-256"] = signature
    return client.post("/webhooks/whatsapp", content=body, headers=headers)


def test_returns_metas_challenge_for_the_configured_verify_token(client):
    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "12345",
        },
    )

    assert response.status_code == 200
    assert response.text == "12345"
    assert response.headers["content-type"].startswith("text/plain")


@pytest.mark.parametrize(
    "params",
    [
        {"hub.mode": "subscribe", "hub.verify_token": "wrong-token", "hub.challenge": "12345"},
        {"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN},
        {"hub.mode": "unsubscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "12345"},
        {},
    ],
    ids=["wrong token", "no challenge", "wrong mode", "no params"],
)
def test_refuses_verification_unless_mode_token_and_challenge_all_match(client, params):
    response = client.get("/webhooks/whatsapp", params=params)

    assert response.status_code == 403
    assert response.json() == {"error": "webhook_verification_failed"}


def test_accepts_a_webhook_only_when_the_raw_payload_signature_matches(client, sign):
    body = webhook_body({"messages": []})

    response = post_webhook(client, body, sign(body))

    assert response.status_code == 200
    assert response.json() == {"received": True}


def test_rejects_an_invalid_webhook_signature(client):
    response = post_webhook(client, b'{"entry": []}', "sha256=00")

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_webhook_signature"}


def test_rejects_an_unsigned_body_before_parsing_it(client):
    response = post_webhook(client, b"definitely not json", None)

    assert response.status_code == 401


def test_rejects_a_signed_body_that_is_not_valid_json(client, sign):
    body = b"definitely not json"

    response = post_webhook(client, body, sign(body))

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_webhook_payload"}


def test_logs_an_inbound_photo_without_the_full_phone_number(client, sign, caplog):
    body = webhook_body({"messages": [MEDICINE_PHOTO]})

    with caplog.at_level(logging.INFO):
        response = post_webhook(client, body, sign(body))

    assert response.status_code == 200
    assert "WhatsApp inbound message accepted" in caplog.text
    for expected in (
        "wa_message_id=wamid.PHOTO1",
        "sender_suffix=1234",
        "message_type=image",
        "media_id=MEDIA-77",
    ):
        assert expected in caplog.text
    assert "966500001234" not in caplog.text


def test_logs_a_delivery_status(client, sign, caplog):
    body = webhook_body(
        {
            "statuses": [
                {
                    "id": "wamid.OUT1",
                    "status": "failed",
                    "errors": [{"code": 131026, "title": "Message undeliverable"}],
                }
            ]
        }
    )

    with caplog.at_level(logging.INFO):
        response = post_webhook(client, body, sign(body))

    assert response.status_code == 200
    assert "WhatsApp delivery status accepted" in caplog.text
    assert "wa_message_id=wamid.OUT1" in caplog.text
    assert "delivery_status=failed" in caplog.text
    assert "error_code=131026" in caplog.text
    assert "error_title=Message undeliverable" in caplog.text


def test_accepts_an_interactive_medication_reply_as_a_button(client, sign, caplog):
    body = webhook_body(
        {
            "messages": [
                {
                    "id": "wamid.REPLY1",
                    "from": "966500001234",
                    "type": "interactive",
                    "interactive": {
                        "type": "button_reply",
                        "button_reply": {"id": "taken", "title": "1"},
                    },
                }
            ]
        }
    )

    with caplog.at_level(logging.INFO):
        response = post_webhook(client, body, sign(body))

    assert response.status_code == 200
    assert "message_type=button" in caplog.text
