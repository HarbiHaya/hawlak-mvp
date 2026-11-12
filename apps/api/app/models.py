from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class PatientCase(Base):
    __tablename__ = "patient_cases"
    __table_args__ = (
        CheckConstraint("expected_box_count > 0", name="ck_patient_cases_expected_box_count"),
        CheckConstraint(
            "status IN ('active', 'photo_collection', 'review_requested', 'completed')",
            name="ck_patient_cases_status",
        ),
        Index("ix_patient_cases_phone_status", "phone_e164", "status"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    patient_alias: Mapped[str] = mapped_column(String(200))
    phone_e164: Mapped[str] = mapped_column(String(16))
    dialect_code: Mapped[str] = mapped_column(String(50))
    expected_box_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CareJourney(Base):
    """Insurer-reviewable discharge journey for the small POC workflow."""

    __tablename__ = "care_journeys"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('draft', 'approved')", name="ck_care_journeys_review_status"
        ),
        Index("ix_care_journeys_review_status", "review_status", "updated_at"),
    )

    case_id: Mapped[str] = mapped_column(
        ForeignKey("patient_cases.id", ondelete="CASCADE"), primary_key=True
    )
    preferred_form_of_address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    language_code: Mapped[str] = mapped_column(String(20))
    source_document: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE)
    discharge_voice_note: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE)
    medications: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE)
    call_plan: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE)
    # Insurer member, eligibility check and enrollment reference.
    insurance: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE, nullable=True)
    # What Hawlak drafted, kept so reviewers can see what was edited.
    generated_draft: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE, nullable=True)
    review_status: Mapped[str] = mapped_column(String(20), default="draft")
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_idempotency_key: Mapped[str | None] = mapped_column(
        String(256), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DeliveryRun(Base):
    __tablename__ = "delivery_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_delivery_runs_idempotency_key"),
        CheckConstraint(
            "kind IN ('discharge_voice_note', 'medication_reminder', 'follow_up_call')",
            name="ck_delivery_runs_kind",
        ),
        CheckConstraint(
            "status IN ('pending', 'claimed', 'sent', 'completed', 'failed', 'transferred')",
            name="ck_delivery_runs_status",
        ),
        Index("ix_delivery_runs_case_status", "case_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("patient_cases.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(256))
    content_ref: Mapped[str] = mapped_column(String(200))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    provider_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_alerts_idempotency_key"),
        CheckConstraint("status IN ('open', 'resolved')", name="ck_alerts_status"),
        Index("ix_alerts_case_status", "case_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("patient_cases.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="open")
    summary: Mapped[str] = mapped_column(String(300))
    idempotency_key: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovedPlan(Base):
    __tablename__ = "approved_plans"
    __table_args__ = (
        UniqueConstraint("case_id", "version", name="uq_approved_plans_case_version"),
        CheckConstraint("version > 0", name="ck_approved_plans_version"),
        Index("ix_approved_plans_case_id", "case_id"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("patient_cases.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer)
    source_hash: Mapped[str] = mapped_column(String(128))
    approved_by: Mapped[str] = mapped_column(String(200))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    clinical_facts: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class VoiceArtifact(Base):
    __tablename__ = "voice_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "plan_id", "prompt_version", name="uq_voice_artifacts_plan_prompt_version"
        ),
        CheckConstraint(
            "approval_status IN ('draft', 'approved', 'rejected')",
            name="ck_voice_artifacts_approval_status",
        ),
        Index("ix_voice_artifacts_plan_id", "plan_id"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("approved_plans.id", ondelete="CASCADE"), nullable=False
    )
    prompt_version: Mapped[str] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    voice: Mapped[str | None] = mapped_column(String(200), nullable=True)
    generated_script_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_script_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="draft")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_script_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    audio_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    audio_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MessageLog(Base):
    __tablename__ = "message_logs"
    __table_args__ = (
        UniqueConstraint("wa_message_id", name="uq_message_logs_wa_message_id"),
        UniqueConstraint("idempotency_key", name="uq_message_logs_idempotency_key"),
        UniqueConstraint("case_id", "outbound_step", name="uq_message_logs_case_outbound_step"),
        CheckConstraint("direction IN ('inbound', 'outbound')", name="ck_message_logs_direction"),
        Index("ix_message_logs_case_created", "case_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    case_id: Mapped[str | None] = mapped_column(
        ForeignKey("patient_cases.id", ondelete="SET NULL"), nullable=True
    )
    wa_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    direction: Mapped[str] = mapped_column(String(16))
    message_type: Mapped[str] = mapped_column(String(32))
    processing_status: Mapped[str] = mapped_column(String(32))
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict)
    outbound_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class InboundMedia(Base):
    __tablename__ = "inbound_media"
    __table_args__ = (
        UniqueConstraint("message_log_id", name="uq_inbound_media_message_log_id"),
        Index("ix_inbound_media_case_received", "case_id", "received_at"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("patient_cases.id", ondelete="CASCADE"), nullable=False
    )
    message_log_id: Mapped[str] = mapped_column(
        ForeignKey("message_logs.id", ondelete="CASCADE"), nullable=False
    )
    meta_media_id: Mapped[str] = mapped_column(String(256))
    mime_type: Mapped[str] = mapped_column(String(100))
    object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    object_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32))
    processing_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_workflow_events_event_id"),
        UniqueConstraint("idempotency_key", name="uq_workflow_events_idempotency_key"),
        CheckConstraint("event_version > 0", name="ck_workflow_events_version"),
        Index("ix_workflow_events_case_sequence", "case_id", "sequence"),
    )

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(128), default=new_id)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("patient_cases.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100))
    event_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE)
    idempotency_key: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewOutcome(Base):
    __tablename__ = "review_outcomes"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_review_outcomes_idempotency_key"),
        CheckConstraint(
            "outcome IN ('matched', 'mismatch_found', 'unclear_photo', 'contact_patient')",
            name="ck_review_outcomes_outcome",
        ),
        Index("ix_review_outcomes_event", "workflow_event_sequence"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    workflow_event_sequence: Mapped[int] = mapped_column(
        ForeignKey("workflow_events.sequence", ondelete="CASCADE"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(32))
    reviewer_id: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
