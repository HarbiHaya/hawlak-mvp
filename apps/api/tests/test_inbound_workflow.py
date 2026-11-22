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


def seed_run(db_session, plan, provider_ref: str):
    from app.models import DeliveryRun, PatientCase

    seed_case(db_session, plan)
    case_id = db_session.query(PatientCase).first().id
    run = DeliveryRun(
        case_id=case_id,
        kind="medication_reminder",
        status="sent",
        idempotency_key=f"run:{provider_ref}",
        content_ref="medications:MED-1",
        provider_ref=provider_ref,
    )
    db_session.add(run)
    db_session.commit()
    return run


def test_failed_status_fails_the_delivery_run_and_raises_an_alert(db_session, plan):
    from app.models import Alert

    run = seed_run(db_session, plan, "wamid.A")

    InboundWorkflow(db_session, FakeStorage(), FakeWhatsApp()).apply_delivery_status(
        "wamid.A", "failed", 131047
    )

    assert run.status == "failed"
    assert run.provider_ref == "wamid.A|meta:131047"
    alerts = db_session.query(Alert).filter_by(type="delivery_failed").all()
    assert [(a.severity, a.status) for a in alerts] == [("medium", "open")]


def test_failed_status_matches_either_id_of_a_reminder_run(db_session, plan):
    run = seed_run(db_session, plan, "wamid.V,wamid.R")

    InboundWorkflow(db_session, FakeStorage(), FakeWhatsApp()).apply_delivery_status(
        "wamid.R", "failed", 131047
    )

    assert run.status == "failed"


def test_failed_status_does_not_match_a_longer_id(db_session, plan):
    run = seed_run(db_session, plan, "wamid.AB")

    InboundWorkflow(db_session, FakeStorage(), FakeWhatsApp()).apply_delivery_status(
        "wamid.A", "failed", 131047
    )

    assert run.status == "sent"


def test_later_delivered_status_does_not_undo_a_failure(db_session, plan):
    from app.models import Alert

    run = seed_run(db_session, plan, "wamid.A")
    workflow = InboundWorkflow(db_session, FakeStorage(), FakeWhatsApp())

    workflow.apply_delivery_status("wamid.A", "failed", 131047)
    workflow.apply_delivery_status("wamid.A", "delivered")
    workflow.apply_delivery_status("wamid.A", "failed", 131047)

    assert run.status == "failed"
    assert db_session.query(Alert).filter_by(type="delivery_failed").count() == 1
