import json

import httpx

from app.main import app
from app.routes.demo import get_whatsapp_client


def test_send_text_sends_the_demo_message_to_the_test_recipient(
    client, fake_meta, internal_auth_headers
):
    whatsapp, seen = fake_meta(httpx.Response(200, json={"messages": [{"id": "wamid.DEMO"}]}))
    app.dependency_overrides[get_whatsapp_client] = lambda: whatsapp

    response = client.post("/internal/demo/send-text", headers=internal_auth_headers)

    assert response.status_code == 202
    assert response.json() == {"messageId": "wamid.DEMO"}
    sent = json.loads(seen[0].content)
    assert sent["to"] == "966500000000"
    assert sent["type"] == "text"


def test_send_text_reports_a_meta_failure_as_bad_gateway(client, fake_meta, internal_auth_headers):
    error = {"error": {"message": "Recipient not in allowed list"}}
    whatsapp, _ = fake_meta(httpx.Response(400, json=error))
    app.dependency_overrides[get_whatsapp_client] = lambda: whatsapp

    response = client.post("/internal/demo/send-text", headers=internal_auth_headers)

    assert response.status_code == 502
    assert response.json() == {
        "error": "meta_api_error",
        "message": "Meta API 400: Recipient not in allowed list",
    }
