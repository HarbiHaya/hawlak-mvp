from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ApprovedPlan, MessageLog, PatientCase, VoiceArtifact
from app.schemas.voice import (
    ApprovedVoiceScript,
    ClinicalFacts,
    DialectComposeRequest,
)
from app.services.audio_first_composer import AudioFirstComposer
from app.services.clinical_fact_guard import compare_clinical_facts
from app.services.dialect_composer import DialectComposer
from app.services.object_storage import ObjectStorage
from app.services.voice_renderer import VoiceRenderer, checksum_script
from app.services.whatsapp_client import WhatsAppClient

DISCLOSURE = "هذا تسجيل صوتي تم إنشاؤه بالذكاء الاصطناعي من خطة خروجك المعتمدة."
PHOTO_REQUEST = "صور لنا علبة كل دواء عندك، وحدة وحدة."
PROMPT_VERSION = "dialect-v2"
AUDIO_FIRST_SESSION_VERSION = "audio-first-v1:session"
AUDIO_FIRST_RECOVERY_VERSION = "audio-first-v1:recovery"


class VoiceWorkflowNotFound(RuntimeError):
    pass


class VoiceWorkflowConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GeneratedScriptResult:
    artifact: VoiceArtifact
    differences: list[dict]


@dataclass(frozen=True, slots=True)
class SendResult:
    artifact: VoiceArtifact
    message_ids: list[str]


@dataclass(frozen=True, slots=True)
class GeneratedAudioFirstResult:
    session_artifact: VoiceArtifact
    recovery_artifact: VoiceArtifact
    approval_checksum: str
    differences: list[dict]


@dataclass(frozen=True, slots=True)
class AudioFirstSendResult:
    session_artifact: VoiceArtifact
    recovery_artifact: VoiceArtifact
    approval_checksum: str
    message_ids: list[str]


class VoiceWorkflow:
    def __init__(
        self,
        session: Session,
        composer: DialectComposer | None,
        renderer: VoiceRenderer,
        storage: ObjectStorage,
        whatsapp: WhatsAppClient,
        audio_first_composer: AudioFirstComposer | None = None,
    ) -> None:
        self.session = session
        self.composer = composer
        self.renderer = renderer
        self.storage = storage
        self.whatsapp = whatsapp
        self.audio_first_composer = audio_first_composer

    async def generate_script(self, case_id: str) -> GeneratedScriptResult:
        if self.composer is None:
            raise VoiceWorkflowConflict("legacy_composer_unavailable")
        patient_case = self.session.get(PatientCase, case_id)
        if patient_case is None:
            raise VoiceWorkflowNotFound(case_id)
        plan = self.session.scalar(
            select(ApprovedPlan)
            .where(ApprovedPlan.case_id == case_id)
            .order_by(ApprovedPlan.version.desc())
        )
        if plan is None:
            raise VoiceWorkflowNotFound(case_id)
        existing = self.session.scalar(
            select(VoiceArtifact).where(
                VoiceArtifact.plan_id == plan.id,
                VoiceArtifact.prompt_version == PROMPT_VERSION,
            )
        )
        if existing is not None:
            return GeneratedScriptResult(existing, [])

        facts = ClinicalFacts.model_validate(plan.clinical_facts)
        composed = await self.composer.compose(
            DialectComposeRequest(
                synthetic=True,
                case_id=patient_case.id,
                plan_id=plan.id,
                source_hash=plan.source_hash,
                patient_alias=patient_case.patient_alias,
                dialect_code=patient_case.dialect_code,
                clinical_facts=facts,
            )
        )
        report = compare_clinical_facts(facts, composed.copied_facts)
        if not report.passed:
            raise VoiceWorkflowConflict("clinical_fact_mismatch")
        checksum = checksum_script(composed.spoken_text_ar)
        artifact = VoiceArtifact(
            plan_id=plan.id,
            prompt_version=PROMPT_VERSION,
            model="configured-composer",
            generated_script_ar=composed.spoken_text_ar,
            generated_script_sha256=checksum,
            approval_status="draft",
        )
        self.session.add(artifact)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise VoiceWorkflowConflict("script_generation_conflict") from exc
        return GeneratedScriptResult(
            artifact,
            [asdict(difference) for difference in report.differences],
        )

    async def generate_audio_first_scripts(self, case_id: str) -> GeneratedAudioFirstResult:
        if self.audio_first_composer is None:
            raise VoiceWorkflowConflict("audio_first_composer_unavailable")
        patient_case = self.session.get(PatientCase, case_id)
        if patient_case is None:
            raise VoiceWorkflowNotFound(case_id)
        plan = self.session.scalar(
            select(ApprovedPlan)
            .where(ApprovedPlan.case_id == case_id)
            .order_by(ApprovedPlan.version.desc())
        )
        if plan is None:
            raise VoiceWorkflowNotFound(case_id)
        session_artifact = self.session.scalar(
            select(VoiceArtifact).where(
                VoiceArtifact.plan_id == plan.id,
                VoiceArtifact.prompt_version == AUDIO_FIRST_SESSION_VERSION,
            )
        )
        recovery_artifact = self.session.scalar(
            select(VoiceArtifact).where(
                VoiceArtifact.plan_id == plan.id,
                VoiceArtifact.prompt_version == AUDIO_FIRST_RECOVERY_VERSION,
            )
        )
        if session_artifact is not None and recovery_artifact is not None:
            return GeneratedAudioFirstResult(
                session_artifact,
                recovery_artifact,
                _audio_first_checksum(session_artifact, recovery_artifact),
                [],
            )
        if session_artifact is not None or recovery_artifact is not None:
            raise VoiceWorkflowConflict("audio_first_generation_conflict")

        facts = ClinicalFacts.model_validate(plan.clinical_facts)
        composed = await self.audio_first_composer.compose(
            DialectComposeRequest(
                synthetic=True,
                case_id=patient_case.id,
                plan_id=plan.id,
                source_hash=plan.source_hash,
                patient_alias=patient_case.patient_alias,
                dialect_code=patient_case.dialect_code,
                clinical_facts=facts,
            )
        )
        report = compare_clinical_facts(facts, composed.copied_facts)
        if not report.passed:
            raise VoiceWorkflowConflict("clinical_fact_mismatch")
        session_artifact = VoiceArtifact(
            plan_id=plan.id,
            prompt_version=AUDIO_FIRST_SESSION_VERSION,
            model="configured-composer",
            generated_script_ar=composed.session_summary_ar,
            generated_script_sha256=checksum_script(composed.session_summary_ar),
            approval_status="draft",
        )
        recovery_artifact = VoiceArtifact(
            plan_id=plan.id,
            prompt_version=AUDIO_FIRST_RECOVERY_VERSION,
            model="configured-composer",
            generated_script_ar=composed.recovery_warning_ar,
            generated_script_sha256=checksum_script(composed.recovery_warning_ar),
            approval_status="draft",
        )
        self.session.add_all([session_artifact, recovery_artifact])
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise VoiceWorkflowConflict("audio_first_generation_conflict") from exc
        return GeneratedAudioFirstResult(
            session_artifact,
            recovery_artifact,
            _audio_first_checksum(session_artifact, recovery_artifact),
            [asdict(difference) for difference in report.differences],
        )

    async def approve_audio_first_and_send(
        self,
        *,
        case_id: str,
        session_artifact_id: str,
        recovery_artifact_id: str,
        approval_checksum: str,
        approved_by: str,
        idempotency_key: str,
    ) -> AudioFirstSendResult:
        patient_case = self.session.get(PatientCase, case_id)
        session_artifact = self.session.get(VoiceArtifact, session_artifact_id)
        recovery_artifact = self.session.get(VoiceArtifact, recovery_artifact_id)
        if patient_case is None or session_artifact is None or recovery_artifact is None:
            raise VoiceWorkflowNotFound(case_id)
        if (
            session_artifact.plan_id != recovery_artifact.plan_id
            or session_artifact.prompt_version != AUDIO_FIRST_SESSION_VERSION
            or recovery_artifact.prompt_version != AUDIO_FIRST_RECOVERY_VERSION
            or _audio_first_checksum(session_artifact, recovery_artifact) != approval_checksum
        ):
            raise VoiceWorkflowConflict("script_checksum_conflict")
        plan = self.session.get(ApprovedPlan, session_artifact.plan_id)
        if plan is None or plan.case_id != case_id:
            raise VoiceWorkflowNotFound(case_id)
        for artifact in (session_artifact, recovery_artifact):
            if artifact.approval_status not in {"draft", "approved"}:
                raise VoiceWorkflowConflict("script_not_approvable")
            artifact.approval_status = "approved"
            artifact.approved_script_sha256 = artifact.generated_script_sha256
            artifact.approved_by = approved_by
            artifact.approved_at = artifact.approved_at or datetime.now(UTC)
        self.session.commit()

        session_audio = await self._render_or_load_audio(session_artifact, case_id, approved_by)
        recovery_audio = await self._render_or_load_audio(recovery_artifact, case_id, approved_by)

        async def send_audio(artifact: VoiceArtifact, audio: bytes, filename: str) -> str:
            media_id = await self.whatsapp.upload_audio(audio, filename)
            return await self.whatsapp.send_audio(patient_case.phone_e164, media_id)

        message_ids = [
            await self._send_step(
                patient_case,
                "session_summary_audio",
                "audio",
                idempotency_key,
                lambda: send_audio(session_artifact, session_audio, f"hawlak-{case_id}-1.ogg"),
                session_artifact,
            ),
            await self._send_step(
                patient_case,
                "recovery_warning_audio",
                "audio",
                idempotency_key,
                lambda: send_audio(recovery_artifact, recovery_audio, f"hawlak-{case_id}-2.ogg"),
                recovery_artifact,
            ),
        ]
        return AudioFirstSendResult(
            session_artifact,
            recovery_artifact,
            approval_checksum,
            message_ids,
        )

    async def _render_or_load_audio(
        self,
        artifact: VoiceArtifact,
        case_id: str,
        approved_by: str,
    ) -> bytes:
        if artifact.audio_object_key:
            return self.storage.get_bytes(artifact.audio_object_key)
        if not artifact.generated_script_ar or not artifact.generated_script_sha256:
            raise VoiceWorkflowConflict("script_checksum_conflict")
        rendered = await self.renderer.render(
            ApprovedVoiceScript(
                artifact_id=artifact.id,
                case_id=case_id,
                synthetic=True,
                spoken_text_ar=artifact.generated_script_ar,
                script_checksum=artifact.generated_script_sha256,
                approved=True,
                approved_by=approved_by,
            )
        )
        stored = self.storage.store_case_media(
            case_id=case_id,
            content=rendered.audio,
            content_type="audio/ogg",
            source_media_id=f"voice-{artifact.id}",
        )
        artifact.audio_object_key = stored.key
        artifact.audio_checksum = rendered.audio_checksum
        artifact.model = rendered.model_id
        artifact.voice = rendered.voice_id
        self.session.commit()
        return rendered.audio

    async def approve_and_send(
        self,
        *,
        case_id: str,
        artifact_id: str,
        script_checksum: str,
        approved_by: str,
        idempotency_key: str,
    ) -> SendResult:
        patient_case = self.session.get(PatientCase, case_id)
        artifact = self.session.get(VoiceArtifact, artifact_id)
        if patient_case is None or artifact is None:
            raise VoiceWorkflowNotFound(case_id)
        plan = self.session.get(ApprovedPlan, artifact.plan_id)
        if plan is None or plan.case_id != case_id:
            raise VoiceWorkflowNotFound(case_id)
        if (
            not artifact.generated_script_ar
            or artifact.generated_script_sha256 != script_checksum
            or checksum_script(artifact.generated_script_ar) != script_checksum
        ):
            raise VoiceWorkflowConflict("script_checksum_conflict")
        if artifact.approval_status not in {"draft", "approved"}:
            raise VoiceWorkflowConflict("script_not_approvable")
        if artifact.approval_status == "approved" and (
            artifact.approved_script_sha256 != script_checksum
            or artifact.approved_by != approved_by
        ):
            raise VoiceWorkflowConflict("approval_conflict")

        artifact.approval_status = "approved"
        artifact.approved_script_sha256 = script_checksum
        artifact.approved_by = approved_by
        artifact.approved_at = artifact.approved_at or datetime.now(UTC)
        self.session.commit()

        if artifact.audio_object_key:
            audio = self.storage.get_bytes(artifact.audio_object_key)
            audio_checksum = artifact.audio_checksum or ""
        else:
            rendered = await self.renderer.render(
                ApprovedVoiceScript(
                    artifact_id=artifact.id,
                    case_id=case_id,
                    synthetic=True,
                    spoken_text_ar=artifact.generated_script_ar,
                    script_checksum=script_checksum,
                    approved=True,
                    approved_by=approved_by,
                )
            )
            stored = self.storage.store_case_media(
                case_id=case_id,
                content=rendered.audio,
                content_type="audio/ogg",
                source_media_id=f"voice-{artifact.id}",
            )
            artifact.audio_object_key = stored.key
            artifact.audio_checksum = rendered.audio_checksum
            artifact.model = rendered.model_id
            artifact.voice = rendered.voice_id
            self.session.commit()
            audio = rendered.audio
            audio_checksum = rendered.audio_checksum

        message_ids = []
        message_ids.append(
            await self._send_step(
                patient_case,
                "disclosure",
                "text",
                idempotency_key,
                lambda: self.whatsapp.send_text(patient_case.phone_e164, DISCLOSURE),
                artifact,
            )
        )

        async def send_audio() -> str:
            media_id = await self.whatsapp.upload_audio(audio, f"hawlak-{case_id}.ogg")
            return await self.whatsapp.send_audio(patient_case.phone_e164, media_id)

        message_ids.append(
            await self._send_step(
                patient_case,
                "audio",
                "audio",
                idempotency_key,
                send_audio,
                artifact,
            )
        )
        message_ids.append(
            await self._send_step(
                patient_case,
                "photo_request",
                "text",
                idempotency_key,
                lambda: self.whatsapp.send_text(patient_case.phone_e164, PHOTO_REQUEST),
                artifact,
            )
        )
        artifact.audio_checksum = audio_checksum
        self.session.commit()
        return SendResult(artifact, message_ids)

    async def _send_step(
        self,
        patient_case: PatientCase,
        step: str,
        message_type: str,
        request_key: str,
        send,
        artifact: VoiceArtifact,
    ) -> str:
        existing = self.session.scalar(
            select(MessageLog).where(
                MessageLog.case_id == patient_case.id,
                MessageLog.outbound_step == step,
            )
        )
        if existing is not None and existing.wa_message_id and existing.delivery_status != "failed":
            return existing.wa_message_id
        wa_message_id = await send()
        if existing is None:
            existing = MessageLog(
                case_id=patient_case.id,
                direction="outbound",
                message_type=message_type,
                outbound_step=step,
                idempotency_key=f"{request_key}:{step}",
            )
            self.session.add(existing)
        existing.wa_message_id = wa_message_id
        existing.processing_status = "sent"
        existing.delivery_status = None
        existing.normalized_payload = {
            "artifactId": artifact.id,
            "scriptChecksum": artifact.approved_script_sha256,
        }
        self.session.commit()
        return wa_message_id


def _audio_first_checksum(
    session_artifact: VoiceArtifact,
    recovery_artifact: VoiceArtifact,
) -> str:
    if not session_artifact.generated_script_ar or not recovery_artifact.generated_script_ar:
        raise VoiceWorkflowConflict("script_checksum_conflict")
    canonical = (
        "session_summary\n"
        + session_artifact.generated_script_ar
        + "\nrecovery_warning\n"
        + recovery_artifact.generated_script_ar
    )
    return checksum_script(canonical)
