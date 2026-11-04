from hashlib import sha256

import pytest

from app.models import MessageLog, VoiceArtifact
from app.schemas.approved_plan import ApprovedPlanDocument
from app.services.case_service import CaseService
from app.services.dialect_composer import MockDialectComposer
from app.services.object_storage import StoredObject
from app.services.voice_renderer import MockVoiceRenderer
from app.services.voice_workflow import VoiceWorkflow, VoiceWorkflowConflict


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def store_case_media(self, *, case_id, content, content_type, source_media_id):
        key = f"cases/{case_id}/media/{source_media_id}.ogg"
        self.objects[key] = content
        return StoredObject(
            key=key,
            size=len(content),
            sha256=sha256(content).hexdigest(),
            etag="fake",
            content_type=content_type,
        )

    def get_bytes(self, key):
        return self.objects[key]


class FakeWhatsApp:
    def __init__(self):
        self.calls = []

    async def send_text(self, to, text):
        self.calls.append(("text", to, text))
        return f"wamid.{len(self.calls)}"

    async def upload_audio(self, audio, filename):
        self.calls.append(("upload", filename, audio))
        return "meta-audio-1"

    async def send_audio(self, to, media_id):
        self.calls.append(("audio", to, media_id))
        return f"wamid.{len(self.calls)}"


class FailAudioOnceWhatsApp(FakeWhatsApp):
    def __init__(self):
        super().__init__()
        self.fail_audio = True

    async def send_audio(self, to, media_id):
        self.calls.append(("audio", to, media_id))
        if self.fail_audio:
            self.fail_audio = False
            raise RuntimeError("temporary Meta failure")
        return f"wamid.{len(self.calls)}"


def workflow(db_session, plan):
    CaseService(db_session).create_case(ApprovedPlanDocument.model_validate(plan), "+966500000000")
    storage = FakeStorage()
    whatsapp = FakeWhatsApp()
    return (
        VoiceWorkflow(
            db_session,
            MockDialectComposer(),
            MockVoiceRenderer(),
            storage,
            whatsapp,
        ),
        storage,
        whatsapp,
    )


@pytest.mark.anyio
async def test_generate_approve_send_is_ordered_and_replay_safe(db_session, plan):
    service, storage, whatsapp = workflow(db_session, plan)
    generated = await service.generate_script("case_01")
    checksum = generated.artifact.generated_script_sha256

    first = await service.approve_and_send(
        case_id="case_01",
        artifact_id=generated.artifact.id,
        script_checksum=checksum,
        approved_by="reviewer-1",
        idempotency_key="send-1",
    )
    second = await service.approve_and_send(
        case_id="case_01",
        artifact_id=generated.artifact.id,
        script_checksum=checksum,
        approved_by="reviewer-1",
        idempotency_key="send-1",
    )

    assert [call[0] for call in whatsapp.calls] == ["text", "upload", "audio", "text"]
    assert first.message_ids == second.message_ids
    assert db_session.query(MessageLog).filter_by(direction="outbound").count() == 3
    assert len(storage.objects) == 1
    assert db_session.query(VoiceArtifact).one().approval_status == "approved"


@pytest.mark.anyio
async def test_wrong_script_checksum_cannot_send(db_session, plan):
    service, _, whatsapp = workflow(db_session, plan)
    generated = await service.generate_script("case_01")

    with pytest.raises(VoiceWorkflowConflict):
        await service.approve_and_send(
            case_id="case_01",
            artifact_id=generated.artifact.id,
            script_checksum="sha256:" + "0" * 64,
            approved_by="reviewer-1",
            idempotency_key="send-1",
        )
    assert whatsapp.calls == []


@pytest.mark.anyio
async def test_retry_resumes_after_last_persisted_outbound_step(db_session, plan):
    service, storage, _ = workflow(db_session, plan)
    whatsapp = FailAudioOnceWhatsApp()
    service = VoiceWorkflow(
        db_session,
        MockDialectComposer(),
        MockVoiceRenderer(),
        storage,
        whatsapp,
    )
    generated = await service.generate_script("case_01")
    approval = {
        "case_id": "case_01",
        "artifact_id": generated.artifact.id,
        "script_checksum": generated.artifact.generated_script_sha256,
        "approved_by": "reviewer-1",
        "idempotency_key": "send-1",
    }

    with pytest.raises(RuntimeError, match="temporary Meta failure"):
        await service.approve_and_send(**approval)
    result = await service.approve_and_send(**approval)

    assert [call[0] for call in whatsapp.calls] == [
        "text",
        "upload",
        "audio",
        "upload",
        "audio",
        "text",
    ]
    assert len(result.message_ids) == 3
    assert db_session.query(MessageLog).filter_by(direction="outbound").count() == 3


@pytest.mark.anyio
async def test_retry_replaces_failed_delivery_ids_without_duplicate_logs(db_session, plan):
    service, _, whatsapp = workflow(db_session, plan)
    generated = await service.generate_script("case_01")
    approval = {
        "case_id": "case_01",
        "artifact_id": generated.artifact.id,
        "script_checksum": generated.artifact.generated_script_sha256,
        "approved_by": "reviewer-1",
        "idempotency_key": "send-1",
    }

    first = await service.approve_and_send(**approval)
    logs = db_session.query(MessageLog).filter_by(direction="outbound").all()
    for log in logs:
        log.delivery_status = "failed"
    db_session.commit()

    second = await service.approve_and_send(**approval)

    assert [call[0] for call in whatsapp.calls] == [
        "text",
        "upload",
        "audio",
        "text",
        "text",
        "upload",
        "audio",
        "text",
    ]
    assert first.message_ids != second.message_ids
    assert db_session.query(MessageLog).filter_by(direction="outbound").count() == 3
    assert {log.delivery_status for log in logs} == {None}
