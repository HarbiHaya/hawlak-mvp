from types import SimpleNamespace

from app.models import InboundMedia, MessageLog, PatientCase
from app.routes import reminders


class FakeReminderWhatsApp:
    def __init__(self):
        self.calls = []

    async def upload_audio(self, audio, filename):
        self.calls.append(("upload_audio", audio, filename))
        return "https://media.example/reminder.ogg"

    async def send_audio(self, to, media_id):
        self.calls.append(("send_audio", to, media_id))
        return "MM-voice"

    async def send_photo_reminder(self, to, *, object_key, content_type):
        self.calls.append(("send_photo_reminder", to, object_key, content_type))
        return "MM-card"


class FakeRenderer:
    async def render(self, script):
        assert "اضغطي واحد" in script.spoken_text_ar
        assert "اثنين" in script.spoken_text_ar
        return SimpleNamespace(
            audio=b"OggS-reminder",
            audio_checksum="sha256:" + "a" * 64,
        )


def seed_stored_photo(db_session):
    case = PatientCase(
        id="case_01",
        patient_alias="أبو محمد",
        phone_e164="+966500000000",
        dialect_code="ar-SA-najdi",
        expected_box_count=1,
        status="review_requested",
    )
    inbound = MessageLog(
        id="message_01",
        case_id="case_01",
        wa_message_id="MM-inbound-photo",
        direction="inbound",
        message_type="image",
        processing_status="processed",
        normalized_payload={},
    )
    photo = InboundMedia(
        id="media_01",
        case_id="case_01",
        message_log_id="message_01",
        meta_media_id="twilio-photo",
        mime_type="image/jpeg",
        object_key="cases/case_01/media/photo.jpg",
        object_sha256="a" * 64,
        processing_status="stored",
    )
    db_session.add_all([case, inbound, photo])
    db_session.commit()


def test_audio_guided_numeric_reminder_is_sent_once(
    client,
    internal_auth_headers,
    db_session,
    monkeypatch,
):
    seed_stored_photo(db_session)
    whatsapp = FakeReminderWhatsApp()
    monkeypatch.setattr(reminders, "ObjectStorage", lambda settings: object())
    monkeypatch.setattr(reminders, "build_whatsapp_client", lambda settings, storage: whatsapp)
    monkeypatch.setattr(reminders, "TwilioWhatsAppClient", FakeReminderWhatsApp)
    monkeypatch.setattr(reminders, "build_voice_renderer", lambda settings: FakeRenderer())
    headers = {**internal_auth_headers, "Idempotency-Key": "reminder-action-1"}
    body = {"mediaId": "media_01", "reminderId": "morning-dose"}

    sent = client.post(
        "/internal/cases/case_01/send-photo-reminder",
        headers=headers,
        json=body,
    )
    replay = client.post(
        "/internal/cases/case_01/send-photo-reminder",
        headers=headers,
        json=body,
    )

    assert sent.status_code == 200
    assert sent.json() == {
        "voiceMessageId": "MM-voice",
        "messageId": "MM-card",
        "mediaId": "media_01",
    }
    assert replay.json() == sent.json()
    assert [call[0] for call in whatsapp.calls] == [
        "upload_audio",
        "send_audio",
        "send_photo_reminder",
    ]
    outbound = db_session.query(MessageLog).filter_by(direction="outbound").all()
    assert {item.message_type for item in outbound} == {"audio", "interactive"}
    assert {item.normalized_payload.get("reminderId") for item in outbound} == {"morning-dose"}
