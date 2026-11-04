from hashlib import sha256

import pytest

from app.models import InboundMedia, MessageLog, WorkflowEvent
from app.schemas.approved_plan import ApprovedPlanDocument
from app.services.case_service import CaseService
from app.services.inbound_workflow import SAFE_REPLY, InboundWorkflow
from app.services.object_storage import StoredObject
from app.services.whatsapp_client import DownloadedMedia


class FakeStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def store_case_media(self, *, case_id, content, content_type, source_media_id):
        key = f"cases/{case_id}/media/{source_media_id}.jpg"
        self.objects[key] = content
        return StoredObject(
            key=key,
            size=len(content),
            sha256=sha256(content).hexdigest(),
            etag="fake",
            content_type=content_type,
        )


class FakeWhatsApp:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def download_image(self, media_id: str):
        return DownloadedMedia(f"image:{media_id}".encode(), "image/jpeg")

    async def send_text(self, to: str, text: str):
        self.sent.append((to, text))
        return f"wamid.sent.{len(self.sent)}"


def seed_case(db_session, plan):
    document = ApprovedPlanDocument.model_validate(plan)
    CaseService(db_session).create_case(document, "+966500000000")


@pytest.mark.anyio
async def test_three_unique_photos_are_stored_once_and_emit_one_event(db_session, plan):
    seed_case(db_session, plan)
    storage = FakeStorage()
    whatsapp = FakeWhatsApp()
    workflow = InboundWorkflow(db_session, storage, whatsapp)

    for number in range(1, 4):
        values = {
            "wa_message_id": f"wamid.{number}",
            "sender": "966500000000",
            "message_type": "image",
            "media_id": f"media-{number}",
            "mime_type": "image/jpeg",
        }
        assert await workflow.ingest_message(**values) is True
        assert await workflow.ingest_message(**values) is False

    assert db_session.query(MessageLog).count() == 3
    assert db_session.query(InboundMedia).count() == 3
    assert (
        db_session.query(WorkflowEvent).filter_by(event_type="pharmacist_review_requested").count()
        == 1
    )
    assert len(storage.objects) == 3
    assert whatsapp.sent == []


@pytest.mark.anyio
async def test_done_requires_at_least_one_stored_photo_and_is_idempotent(db_session, plan):
    seed_case(db_session, plan)
    workflow = InboundWorkflow(db_session, FakeStorage(), FakeWhatsApp())

    await workflow.ingest_message(
        wa_message_id="wamid.done.early",
        sender="966500000000",
        message_type="text",
        text="تم",
    )
    assert db_session.query(WorkflowEvent).count() == 0

    await workflow.ingest_message(
        wa_message_id="wamid.photo",
        sender="966500000000",
        message_type="image",
        media_id="media-1",
        mime_type="image/jpeg",
    )
    await workflow.ingest_message(
        wa_message_id="wamid.done",
        sender="966500000000",
        message_type="text",
        text="تم",
    )
    assert (
        db_session.query(WorkflowEvent).filter_by(event_type="pharmacist_review_requested").count()
        == 1
    )


@pytest.mark.anyio
async def test_unsupported_input_gets_fixed_reply_and_human_review(db_session, plan):
    seed_case(db_session, plan)
    whatsapp = FakeWhatsApp()
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp)

    await workflow.ingest_message(
        wa_message_id="wamid.question",
        sender="966500000000",
        message_type="text",
        text="هل أغير الجرعة؟",
    )

    assert whatsapp.sent == [("+966500000000", SAFE_REPLY)]
    assert (
        db_session.query(WorkflowEvent).filter_by(event_type="human_review_requested").count() == 1
    )


@pytest.mark.anyio
async def test_unmatched_sender_is_persisted_without_side_effects(db_session):
    storage = FakeStorage()
    whatsapp = FakeWhatsApp()

    created = await InboundWorkflow(db_session, storage, whatsapp).ingest_message(
        wa_message_id="wamid.unknown",
        sender="966511111111",
        message_type="image",
        media_id="media-unknown",
    )

    assert created is True
    assert db_session.query(MessageLog).one().processing_status == "unmatched"
    assert storage.objects == {}
    assert whatsapp.sent == []


@pytest.mark.anyio
async def test_quick_reply_is_recorded_without_a_text_response(db_session, plan):
    seed_case(db_session, plan)
    whatsapp = FakeWhatsApp()
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp)

    await workflow.ingest_message(
        wa_message_id="MM.button",
        sender="966500000000",
        message_type="button",
        text="✅ أخذتها",
        button_payload="taken",
    )

    message = db_session.query(MessageLog).filter_by(wa_message_id="MM.button").one()
    assert message.processing_status == "processed"
    assert message.normalized_payload["buttonPayload"] == "taken"
    assert whatsapp.sent == []
