from hashlib import sha256

import pytest

from app.models import MessageLog, VoiceArtifact
from app.schemas.approved_plan import ApprovedPlanDocument
from app.services.audio_first_composer import MockAudioFirstComposer
from app.services.case_service import CaseService
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
        return f"SM{len(self.calls)}"

    async def upload_audio(self, audio, filename):
        self.calls.append(("upload", filename, audio))
        return f"media-{len(self.calls)}"

    async def send_audio(self, to, media_id):
        self.calls.append(("audio", to, media_id))
        return f"MM{len(self.calls)}"


def workflow(db_session, plan):
    CaseService(db_session).create_case(ApprovedPlanDocument.model_validate(plan), "+966500000000")
    storage = FakeStorage()
    whatsapp = FakeWhatsApp()
    service = VoiceWorkflow(
        db_session,
        composer=None,
        renderer=MockVoiceRenderer(),
        storage=storage,
        whatsapp=whatsapp,
        audio_first_composer=MockAudioFirstComposer(),
    )
    return service, storage, whatsapp


@pytest.mark.anyio
async def test_audio_first_flow_generates_two_scripts_and_sends_only_two_audio_notes(
    db_session, plan
):
    service, storage, whatsapp = workflow(db_session, plan)

    generated = await service.generate_audio_first_scripts("case_01")
    result = await service.approve_audio_first_and_send(
        case_id="case_01",
        session_artifact_id=generated.session_artifact.id,
        recovery_artifact_id=generated.recovery_artifact.id,
        approval_checksum=generated.approval_checksum,
        approved_by="reviewer-1",
        idempotency_key="audio-first-1",
    )

    assert "أرسل" in generated.session_artifact.generated_script_ar
    assert "997" in generated.recovery_artifact.generated_script_ar
    assert [call[0] for call in whatsapp.calls] == ["upload", "audio", "upload", "audio"]
    assert len(result.message_ids) == 2
    assert len(storage.objects) == 2
    assert db_session.query(VoiceArtifact).filter_by(approval_status="approved").count() == 2
    assert {
        log.outbound_step
        for log in db_session.query(MessageLog).filter_by(direction="outbound").all()
    } == {"session_summary_audio", "recovery_warning_audio"}


@pytest.mark.anyio
async def test_audio_first_bundle_checksum_binds_both_scripts(db_session, plan):
    service, _, whatsapp = workflow(db_session, plan)
    generated = await service.generate_audio_first_scripts("case_01")

    with pytest.raises(VoiceWorkflowConflict, match="script_checksum_conflict"):
        await service.approve_audio_first_and_send(
            case_id="case_01",
            session_artifact_id=generated.session_artifact.id,
            recovery_artifact_id=generated.recovery_artifact.id,
            approval_checksum="sha256:" + "0" * 64,
            approved_by="reviewer-1",
            idempotency_key="audio-first-1",
        )

    assert whatsapp.calls == []
