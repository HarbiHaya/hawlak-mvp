import json
import logging

import pytest

from scripts.replay_patient import replay


@pytest.fixture
def replay_with(client, settings, plan):
    """replay() wired to the in-process API; returns (statuses, the webhook payloads it sent)."""

    def run(**overrides):
        sent: list[dict] = []

        def post(body: bytes, signature: str) -> int:
            sent.append(json.loads(body))
            headers = {"content-type": "application/json", "x-hub-signature-256": signature}
            return client.post("/webhooks/whatsapp", content=body, headers=headers).status_code

        options = {
            "phone": settings.whatsapp_test_recipient,
            "phone_number_id": settings.whatsapp_phone_number_id,
            "app_secret": settings.meta_app_secret,
            **overrides,
        }
        return replay(plan, post=post, **options), sent

    return run


def message_ids(sent: list[dict]) -> list[str]:
    return [p["entry"][0]["changes"][0]["value"]["messages"][0]["id"] for p in sent]


def test_sends_one_signed_photo_message_per_expected_box(replay_with, caplog):
    with caplog.at_level(logging.INFO):
        statuses, _ = replay_with()

    assert statuses == [200, 200, 200]
    assert caplog.text.count("WhatsApp inbound message accepted") == 3
    assert caplog.text.count("message_type=image") == 3
    assert "sender_suffix=0000" in caplog.text
    assert "966500000000" not in caplog.text


def test_done_adds_a_final_text_message(replay_with, caplog):
    with caplog.at_level(logging.INFO):
        statuses, sent = replay_with(done=True)

    assert statuses == [200, 200, 200, 200]
    assert sent[-1]["entry"][0]["changes"][0]["value"]["messages"][0]["text"] == {"body": "تم"}
    assert "message_type=text" in caplog.text


def test_photos_overrides_the_expected_box_count(replay_with):
    statuses, _ = replay_with(photos=2)

    assert statuses == [200, 200]


def test_repeat_resends_each_message_with_the_same_whatsapp_id(replay_with):
    statuses, sent = replay_with(repeat=True)

    assert len(statuses) == 6
    assert len(set(message_ids(sent))) == 3


def test_a_fixed_run_id_replays_the_same_ids_and_a_new_one_does_not(replay_with):
    _, first = replay_with(run_id="same")
    _, second = replay_with(run_id="same")
    _, third = replay_with()

    assert message_ids(first) == message_ids(second)
    assert set(message_ids(first)).isdisjoint(message_ids(third))


def test_the_api_rejects_a_webhook_signed_with_the_wrong_secret(replay_with):
    statuses, _ = replay_with(app_secret="not-the-app-secret")

    assert statuses == [401, 401, 401]
