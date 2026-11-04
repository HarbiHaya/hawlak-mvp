from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.approved_plan import CamelModel


class ReviewCase(CamelModel):
    case_id: str
    patient_alias: str
    phone_e164_masked: str
    expected_box_count: int
    received_box_count: int


class ReviewPlan(CamelModel):
    plan_id: str
    version: int
    source_hash: str


class MedicinePhoto(CamelModel):
    media_id: str
    object_key: str


class PharmacistReviewRequested(CamelModel):
    event_id: str
    event_type: Literal["pharmacist_review_requested"]
    event_version: Literal[1]
    idempotency_key: str
    occurred_at: datetime
    case: ReviewCase
    approved_plan: ReviewPlan
    medicine_photos: list[MedicinePhoto]
    review_reason: Literal["expected_photo_count_reached", "patient_marked_done"]


class ReviewEventsPage(CamelModel):
    data: list[PharmacistReviewRequested]
    next_cursor: str | None


class ReviewOutcomeRequest(CamelModel):
    event_version: Literal[1]
    outcome: Literal["matched", "mismatch_found", "unclear_photo", "contact_patient"]
    reviewer_id: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class ReviewOutcomeData(CamelModel):
    outcome_id: str
    event_id: str
    event_version: int
    outcome: str
    reviewer_id: str
    note: str | None
    recorded_at: datetime


class ReviewOutcomeResponse(CamelModel):
    data: ReviewOutcomeData
