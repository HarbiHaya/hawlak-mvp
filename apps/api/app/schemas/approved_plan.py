from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.dialects import DialectCode


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class Medicine(CamelModel):
    item_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    strength: str = Field(min_length=1)
    dose: str = Field(min_length=1)
    frequency: str = Field(min_length=1)
    timing: str = Field(min_length=1)


class ClinicalFacts(CamelModel):
    new_medicines: list[Medicine] = Field(min_length=1)
    stopped_medicines: list[str]
    activity_instructions: list[str]
    diet_instructions: list[str]
    red_flags: list[str] = Field(min_length=1)
    emergency_number: str = Field(pattern=r"^\d{3}$")


class CaseDetails(CamelModel):
    case_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    patient_ref: str = Field(min_length=1)
    patient_alias: str = Field(min_length=1)
    dialect_code: DialectCode
    expected_box_count: int = Field(gt=0)


class PlanSource(CamelModel):
    system: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    document: str = Field(min_length=1)
    source_hash: str = Field(min_length=8, max_length=128)


class ApprovedPlanDetails(CamelModel):
    plan_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    version: int = Field(gt=0)
    approved_by: str = Field(min_length=1)
    approved_at: datetime
    source: PlanSource
    clinical_facts: ClinicalFacts


class ApprovedPlanDocument(CamelModel):
    synthetic: Literal[True]
    review_status: str = Field(min_length=1)
    case: CaseDetails
    approved_plan: ApprovedPlanDetails


class CreateCaseRequest(ApprovedPlanDocument):
    demo_recipient: str = Field(pattern=r"^\+[1-9]\d{7,14}$")


class CaseResponse(CamelModel):
    case_id: str
    plan_id: str
    version: int
    status: str


class TimelineEntry(CamelModel):
    type: str
    occurred_at: datetime
    details: dict[str, str | int]


class CaseTimelineResponse(CamelModel):
    case_id: str
    data: list[TimelineEntry]
