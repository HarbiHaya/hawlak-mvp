from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.dialects import DialectCode


class StrictVoiceModel(BaseModel):
    """Base model for safety-critical voice artifacts.

    Provider output is rejected when it is incomplete or contains fields the
    application does not understand.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MedicineFact(StrictVoiceModel):
    item_id: str = Field(alias="itemId", min_length=1)
    name: str = Field(min_length=1)
    strength: str = Field(min_length=1)
    dose: str = Field(min_length=1)
    frequency: str = Field(min_length=1)
    timing: str = Field(min_length=1)


class ClinicalFacts(StrictVoiceModel):
    new_medicines: list[MedicineFact] = Field(alias="newMedicines", min_length=1)
    stopped_medicines: list[str] = Field(alias="stoppedMedicines")
    activity_instructions: list[str] = Field(alias="activityInstructions")
    diet_instructions: list[str] = Field(alias="dietInstructions")
    red_flags: list[str] = Field(alias="redFlags", min_length=1)
    emergency_number: str = Field(alias="emergencyNumber", min_length=1)


class DialectComposeRequest(StrictVoiceModel):
    synthetic: bool
    case_id: str = Field(alias="caseId", min_length=1)
    plan_id: str = Field(alias="planId", min_length=1)
    source_hash: str = Field(alias="sourceHash", pattern=r"^sha256:[0-9a-f]{64}$")
    patient_alias: str = Field(alias="patientAlias", min_length=1)
    dialect_code: DialectCode = Field(alias="dialectCode")
    clinical_facts: ClinicalFacts = Field(alias="clinicalFacts")


class ComposedVoiceScript(StrictVoiceModel):
    patient_alias: str = Field(alias="patientAlias", min_length=1)
    dialect_code: DialectCode = Field(alias="dialectCode")
    spoken_text_ar: str = Field(alias="spokenTextAr", min_length=1)
    copied_facts: ClinicalFacts = Field(alias="copiedFacts")
    prohibited_content_detected: bool = Field(alias="prohibitedContentDetected")
    safety_notes: list[str] = Field(alias="safetyNotes")


class ComposedAudioFirstScripts(StrictVoiceModel):
    patient_alias: str = Field(alias="patientAlias", min_length=1)
    dialect_code: DialectCode = Field(alias="dialectCode")
    session_summary_ar: str = Field(alias="sessionSummaryAr", min_length=1)
    recovery_warning_ar: str = Field(alias="recoveryWarningAr", min_length=1)
    copied_facts: ClinicalFacts = Field(alias="copiedFacts")
    prohibited_content_detected: bool = Field(alias="prohibitedContentDetected")
    safety_notes: list[str] = Field(alias="safetyNotes")


class ApprovedVoiceScript(StrictVoiceModel):
    artifact_id: str = Field(alias="artifactId", min_length=1)
    case_id: str = Field(alias="caseId", min_length=1)
    synthetic: bool
    spoken_text_ar: str = Field(alias="spokenTextAr", min_length=1)
    script_checksum: str = Field(alias="scriptChecksum", pattern=r"^sha256:[0-9a-f]{64}$")
    approved: Literal[True]
    approved_by: str = Field(alias="approvedBy", min_length=1)


class RenderedVoiceArtifact(StrictVoiceModel):
    source_artifact_id: str = Field(alias="sourceArtifactId", min_length=1)
    script_checksum: str = Field(alias="scriptChecksum", pattern=r"^sha256:[0-9a-f]{64}$")
    audio: bytes = Field(min_length=1)
    audio_checksum: str = Field(alias="audioChecksum", pattern=r"^sha256:[0-9a-f]{64}$")
    model_id: str = Field(alias="modelId", min_length=1)
    voice_id: str = Field(alias="voiceId", min_length=1)
    output_format: str = Field(alias="outputFormat", min_length=1)


class GenerateScriptResponse(StrictVoiceModel):
    artifact_id: str = Field(alias="artifactId")
    case_id: str = Field(alias="caseId")
    spoken_text_ar: str = Field(alias="spokenTextAr")
    script_checksum: str = Field(alias="scriptChecksum")
    fact_report: dict[str, Any] = Field(alias="factReport")


class ApproveAndSendRequest(StrictVoiceModel):
    artifact_id: str = Field(alias="artifactId", min_length=1)
    script_checksum: str = Field(alias="scriptChecksum", pattern=r"^sha256:[0-9a-f]{64}$")
    approved_by: str = Field(alias="approvedBy", min_length=1)


class ApproveAndSendResponse(StrictVoiceModel):
    artifact_id: str = Field(alias="artifactId")
    case_id: str = Field(alias="caseId")
    script_checksum: str = Field(alias="scriptChecksum")
    audio_checksum: str = Field(alias="audioChecksum")
    message_ids: list[str] = Field(alias="messageIds")


class AudioFirstScriptPart(StrictVoiceModel):
    kind: Literal["session_summary", "recovery_warning"]
    artifact_id: str = Field(alias="artifactId")
    spoken_text_ar: str = Field(alias="spokenTextAr")
    script_checksum: str = Field(alias="scriptChecksum")


class GenerateAudioFirstResponse(StrictVoiceModel):
    case_id: str = Field(alias="caseId")
    approval_checksum: str = Field(alias="approvalChecksum")
    scripts: list[AudioFirstScriptPart]
    fact_report: dict[str, Any] = Field(alias="factReport")


class ApproveAudioFirstRequest(StrictVoiceModel):
    session_artifact_id: str = Field(alias="sessionArtifactId", min_length=1)
    recovery_artifact_id: str = Field(alias="recoveryArtifactId", min_length=1)
    approval_checksum: str = Field(alias="approvalChecksum", pattern=r"^sha256:[0-9a-f]{64}$")
    approved_by: str = Field(alias="approvedBy", min_length=1)


class ApproveAudioFirstResponse(StrictVoiceModel):
    case_id: str = Field(alias="caseId")
    approval_checksum: str = Field(alias="approvalChecksum")
    audio_checksums: dict[str, str] = Field(alias="audioChecksums")
    message_ids: list[str] = Field(alias="messageIds")


class DialectOption(StrictVoiceModel):
    code: DialectCode
    label_ar: str = Field(alias="labelAr")
    label_en: str = Field(alias="labelEn")


class VoiceProviderOption(StrictVoiceModel):
    provider: Literal["elevenlabs"]
    voice_label: str = Field(alias="voiceLabel")
    model_id: str = Field(alias="modelId")
    language_code: Literal["ar"] = Field(alias="languageCode")


class VoiceOptionsResponse(StrictVoiceModel):
    dialects: list[DialectOption]
    voice: VoiceProviderOption
