from hashlib import sha256

from app.main import app
from app.models import InboundMedia, MessageLog, ReviewOutcome, WorkflowEvent
from app.routes.voice import get_voice_workflow
from app.routes.whatsapp_webhook import get_inbound_workflow
from app.services.dialect_composer import MockDialectComposer
from app.services.inbound_workflow import InboundWorkflow
from app.services.object_storage import StoredObject, get_object_storage
from app.services.voice_renderer import MockVoiceRenderer
from app.services.voice_workflow import VoiceWorkflow
from app.services.whatsapp_client import DownloadedMedia
from scripts.replay_patient import replay


class DemoStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def store_case_media(self, *, case_id, content, content_type, source_media_id):
        extension = "ogg" if content_type == "audio/ogg" else "jpg"
        key = f"cases/{case_id}/media/{source_media_id}.{extension}"
        self.objects[key] = content
        return StoredObject(
            key=key,
            size=len(content),
            sha256=sha256(content).hexdigest(),
            etag="demo",
            content_type=content_type,
        )

    def get_bytes(self, key):
        return self.objects[key]


class DemoWhatsApp:
    def __init__(self):
        self.sent: list[tuple] = []

    async def send_text(self, to, text):
        self.sent.append(("text", to, text))
        return f"wamid.demo.{len(self.sent)}"

    async def upload_audio(self, audio, filename):
        self.sent.append(("upload", filename, audio))
        return "meta-audio-demo"

    async def send_audio(self, to, media_id):
        self.sent.append(("audio", to, media_id))
        return f"wamid.demo.{len(self.sent)}"

    async def download_image(self, media_id):
        return DownloadedMedia(f"synthetic:{media_id}".encode(), "image/jpeg")


def test_complete_synthetic_demo_is_connected_and_replay_safe(
    client,
    db_session,
    internal_auth_headers,
    plan,
    settings,
):
    storage = DemoStorage()
    whatsapp = DemoWhatsApp()
    voice = VoiceWorkflow(
        db_session,
        MockDialectComposer(),
        MockVoiceRenderer(),
        storage,
        whatsapp,
    )
    inbound = InboundWorkflow(db_session, storage, whatsapp)
    app.dependency_overrides[get_voice_workflow] = lambda: voice
    app.dependency_overrides[get_inbound_workflow] = lambda: inbound
    app.dependency_overrides[get_object_storage] = lambda: storage

    case_body = {**plan, "demoRecipient": settings.whatsapp_test_recipient}
    created = client.post("/internal/cases", json=case_body, headers=internal_auth_headers)
    replayed_case = client.post("/internal/cases", json=case_body, headers=internal_auth_headers)
    assert created.status_code == 201
    assert replayed_case.status_code == 200

    generated = client.post(
        "/internal/cases/case_01/generate-script", headers=internal_auth_headers
    )
    assert generated.status_code == 200
    generated_body = generated.json()
    assert generated_body["factReport"] == {"passed": True, "differences": []}

    approval = {
        "artifactId": generated_body["artifactId"],
        "scriptChecksum": generated_body["scriptChecksum"],
        "approvedBy": "demo-reviewer-01",
    }
    approval_headers = {**internal_auth_headers, "Idempotency-Key": "demo-send-01"}
    sent = client.post(
        "/internal/cases/case_01/approve-and-send",
        json=approval,
        headers=approval_headers,
    )
    sent_replay = client.post(
        "/internal/cases/case_01/approve-and-send",
        json=approval,
        headers=approval_headers,
    )
    assert sent.status_code == 200
    assert sent.json() == sent_replay.json()
    assert len(sent.json()["messageIds"]) == 3

    def post_webhook(body: bytes, signature: str) -> int:
        return client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={
                "content-type": "application/json",
                "x-hub-signature-256": signature,
            },
        ).status_code

    statuses = replay(
        plan,
        post=post_webhook,
        phone=settings.whatsapp_test_recipient,
        phone_number_id=settings.whatsapp_phone_number_id,
        app_secret=settings.meta_app_secret,
        done=True,
        repeat=True,
        run_id="e2e",
    )
    assert statuses == [200] * 8
    assert db_session.query(MessageLog).filter_by(direction="outbound").count() == 3
    assert (
        db_session.query(MessageLog).filter_by(direction="inbound", message_type="image").count()
        == 3
    )
    assert db_session.query(InboundMedia).count() == 3
    assert db_session.query(WorkflowEvent).count() == 1
    assert len(storage.objects) == 4  # one approved audio object plus three photos

    page = client.get("/internal/review-events", headers=internal_auth_headers)
    assert page.status_code == 200
    event = page.json()["data"][0]
    assert event["eventType"] == "pharmacist_review_requested"
    assert len(event["medicinePhotos"]) == 3
    empty = client.get(
        "/internal/review-events",
        params={"after": page.json()["nextCursor"]},
        headers=internal_auth_headers,
    )
    assert empty.json()["data"] == []

    outcome_headers = {**internal_auth_headers, "Idempotency-Key": "demo-outcome-01"}
    outcome_body = {
        "eventVersion": 1,
        "outcome": "matched",
        "reviewerId": "demo-pharmacist-01",
    }
    outcome_url = f"/internal/review-events/{event['eventId']}/outcomes"
    first_outcome = client.post(outcome_url, json=outcome_body, headers=outcome_headers)
    second_outcome = client.post(outcome_url, json=outcome_body, headers=outcome_headers)
    assert first_outcome.status_code == 201
    assert second_outcome.status_code == 200
    assert first_outcome.json() == second_outcome.json()
    assert db_session.query(ReviewOutcome).count() == 1

    timeline = client.get("/internal/cases/case_01/timeline", headers=internal_auth_headers)
    assert timeline.status_code == 200
    timeline_types = {entry["type"] for entry in timeline.json()["data"]}
    assert {
        "case_created",
        "approved_plan_loaded",
        "voice_script_generated",
        "voice_script_approved",
        "whatsapp_outbound_text",
        "whatsapp_outbound_audio",
        "whatsapp_inbound_image",
        "medicine_photo_stored",
        "workflow_event_created",
        "review_outcome_recorded",
    } <= timeline_types
