from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.dialects import DialectCode


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class SourceDocument(CamelModel):
    object_key: str = Field(min_length=1, max_length=1024)
    filename: str = Field(min_length=1, max_length=255)


class DischargeVoiceNote(CamelModel):
    enabled: bool = True
    script: str = Field(min_length=1, max_length=6000)


class MedicationImage(CamelModel):
    source: Literal["catalog", "patient_photo"]
    object_key: str = Field(min_length=1, max_length=1024)
    review_status: Literal["pending", "approved", "rejected"]
    ocr_candidate: str | None = Field(default=None, max_length=300)


class JourneyMedication(CamelModel):
    medication_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    dose_instruction: str = Field(min_length=1, max_length=500)
    dispensed: bool
    image: MedicationImage | None = None
    reminder_enabled: bool
    reminder_script: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_reminder(self):
        if self.reminder_enabled and not self.dispensed:
            raise ValueError("a reminder cannot be enabled before medication is dispensed")
        return self


class CallQuestion(CamelModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    prompt: str = Field(min_length=1, max_length=1000)


class CallPlan(CamelModel):
    enabled: bool
    scheduled_after_hours: int = Field(ge=0, le=168)
    opening_script: str = Field(min_length=1, max_length=2000)
    questions: list[CallQuestion] = Field(min_length=1, max_length=12)
    completion_script: str = Field(min_length=1, max_length=1000)
    transfer_script: str = Field(min_length=1, max_length=1000)
    transfer_target: str = Field(min_length=1, max_length=100)
    responder_phone_e164: str = Field(pattern=r"^\+[1-9]\d{7,14}$")


class CareJourneyCreate(CamelModel):
    case_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    patient_name: str = Field(min_length=2, max_length=200)
    preferred_form_of_address: str | None = Field(default=None, max_length=200)
    phone_e164: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    language_code: Literal["ar", "en"]
    dialect_code: DialectCode
    source_document: SourceDocument
    discharge_voice_note: DischargeVoiceNote | None = None
    medications: list[JourneyMedication] | None = Field(default=None, max_length=20)
    call_plan: CallPlan | None = None


class CareJourneyContent(CamelModel):
    discharge_voice_note: DischargeVoiceNote
    medications: list[JourneyMedication] = Field(min_length=1, max_length=20)
    call_plan: CallPlan


class ApprovalRequest(CamelModel):
    approved_by: str = Field(min_length=1, max_length=200)


class DeliveryRunView(CamelModel):
    id: str
    kind: str
    status: str
    scheduled_at: datetime


class DeliveryRunUpdate(CamelModel):
    status: Literal["sent", "completed", "failed", "transferred"]
    provider_ref: str | None = Field(default=None, max_length=256)


class CallEscalation(CamelModel):
    question_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    answer_kind: Literal["red_flag", "uncertain", "transfer_request"]


class CallOutcomeRequest(CamelModel):
    status: Literal["completed", "transferred"]
    provider_ref: str | None = Field(default=None, max_length=256)
    escalation: CallEscalation | None = None

    @model_validator(mode="after")
    def validate_escalation(self):
        if self.status == "transferred" and self.escalation is None:
            raise ValueError("a transferred call requires an escalation")
        if self.status == "completed" and self.escalation is not None:
            raise ValueError("a completed call cannot include an escalation")
        return self


class CallPlanView(CamelModel):
    id: str
    case_id: str
    version: int
    approved_at: datetime
    phone_e164: str
    participant_label: str
    language: str
    opening_script: str
    questions: list[CallQuestion]
    completion_script: str
    transfer_script: str
    responder_phone_e164: str
