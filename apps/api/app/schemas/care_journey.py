from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.dialects import DialectCode
from app.services.dose_facts import REMINDER_TIME

MEMBER_ID = r"^[A-Za-z0-9-]{4,32}$"


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class SourceDocument(CamelModel):
    object_key: str = Field(min_length=1, max_length=1024)
    filename: str = Field(min_length=1, max_length=255)


# Draft content may be incomplete. CareJourneyService.approve enforces completeness.
class DischargeVoiceNote(CamelModel):
    enabled: bool = True
    script: str = Field(max_length=6000)


class MedicationImage(CamelModel):
    source: Literal["catalog", "patient_photo"]
    object_key: str = Field(min_length=1, max_length=1024)
    review_status: Literal["pending", "approved", "rejected"]
    ocr_candidate: str | None = Field(default=None, max_length=300)


class JourneyMedication(CamelModel):
    medication_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(max_length=200)
    dose_instruction: str = Field(max_length=500)
    dispensed: bool
    image: MedicationImage | None = None
    reminder_enabled: bool
    reminder_script: str = Field(max_length=1000)
    # Confirmed strength of one dispensed tablet or capsule, e.g. "40 mg". See dose_facts.
    unit_strength: str | None = Field(default=None, max_length=50)
    # Chosen reminder clock times, 24-hour HH:MM in Saudi time.
    reminder_times: list[Annotated[str, Field(pattern=REMINDER_TIME)]] = Field(
        default_factory=list, max_length=6
    )

    @model_validator(mode="after")
    def validate_reminder(self):
        if self.reminder_enabled and not self.dispensed:
            raise ValueError("a reminder cannot be enabled before medication is dispensed")
        return self


class CallQuestion(CamelModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    prompt: str = Field(max_length=1000)


class CallPlan(CamelModel):
    enabled: bool
    # First call: an exact time when set, otherwise this many hours after approval.
    scheduled_after_hours: int = Field(default=24, ge=0, le=168)
    first_call_at: datetime | None = None
    repeat: Literal["none", "daily", "every_2_days", "weekly"] = "none"
    occurrences: int = Field(default=1, ge=1, le=14)
    opening_script: str = Field(max_length=2000)
    questions: list[CallQuestion] = Field(max_length=12)
    completion_script: str = Field(max_length=1000)
    transfer_script: str = Field(max_length=1000)
    transfer_target: str = Field(max_length=100)
    responder_phone_e164: str = Field(pattern=r"^(\+[1-9]\d{7,14})?$")


class CareJourneyCreate(CamelModel):
    case_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    patient_name: str = Field(min_length=2, max_length=200)
    preferred_form_of_address: str | None = Field(default=None, max_length=200)
    phone_e164: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    # Registered with the caregiver's consent; this number may send medicine photos.
    caregiver_phone_e164: str | None = Field(default=None, pattern=r"^\+[1-9]\d{7,14}$")
    member_id: str | None = Field(default=None, pattern=MEMBER_ID)
    language_code: Literal["ar", "en"]
    dialect_code: DialectCode
    source_document: SourceDocument
    discharge_voice_note: DischargeVoiceNote | None = None
    medications: list[JourneyMedication] | None = Field(default=None, max_length=20)
    call_plan: CallPlan | None = None

    @model_validator(mode="after")
    def validate_caregiver(self):
        if self.caregiver_phone_e164 and self.caregiver_phone_e164 == self.phone_e164:
            raise ValueError("the caregiver phone must differ from the patient phone")
        return self


class CareJourneyContent(CamelModel):
    discharge_voice_note: DischargeVoiceNote
    medications: list[JourneyMedication] = Field(max_length=20)
    call_plan: CallPlan


class EligibilityRequest(CamelModel):
    member_id: str = Field(pattern=MEMBER_ID)


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


class PhotoReviewRequest(CamelModel):
    decision: Literal["confirmed", "follow_up"]
    reviewed_by: str = Field(min_length=1, max_length=200)


class CallEscalation(CamelModel):
    question_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    answer_kind: Literal["red_flag", "uncertain", "transfer_request"]


class CallOutcomeRequest(CamelModel):
    status: Literal["completed", "transferred", "failed"]
    provider_ref: str | None = Field(default=None, max_length=256)
    escalation: CallEscalation | None = None

    @model_validator(mode="after")
    def validate_escalation(self):
        if self.status in {"transferred", "failed"} and self.escalation is None:
            raise ValueError(f"a {self.status} call requires an escalation")
        if self.status == "completed" and self.escalation is not None:
            raise ValueError("a completed call cannot include an escalation")
        return self


class CallTurnIn(CamelModel):
    seq: int = Field(ge=1, le=1000)
    speaker: Literal["agent", "patient"]
    text: str = Field(max_length=2000)
    answer_kind: str | None = Field(default=None, max_length=32)
    guard: Literal["ok", "replaced"] | None = None


class CallTurnsRequest(CamelModel):
    turns: list[CallTurnIn] = Field(max_length=400)


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
