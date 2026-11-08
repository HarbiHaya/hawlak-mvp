import logging
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    ApprovedPlan,
    InboundMedia,
    MessageLog,
    PatientCase,
    ReviewOutcome,
    VoiceArtifact,
    WorkflowEvent,
)
from app.schemas.approved_plan import ApprovedPlanDocument

logger = logging.getLogger(__name__)


class CaseConflictError(RuntimeError):
    """The requested case/version exists with different immutable content."""


class CaseNotFoundError(RuntimeError):
    """No synthetic case exists for the requested ID."""


@dataclass(frozen=True, slots=True)
class CreateCaseResult:
    case: PatientCase
    plan: ApprovedPlan
    created: bool


class CaseService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_case(self, document: ApprovedPlanDocument, phone_e164: str) -> CreateCaseResult:
        case_input = document.case
        plan_input = document.approved_plan
        existing_case = self.session.get(PatientCase, case_input.case_id)
        existing_plan = self.session.scalar(
            select(ApprovedPlan).where(
                ApprovedPlan.case_id == case_input.case_id,
                ApprovedPlan.version == plan_input.version,
            )
        )

        if existing_case is not None:
            if not self._same_case(existing_case, document, phone_e164):
                raise CaseConflictError("case_conflict")
            if existing_plan is not None:
                if not self._same_plan(existing_plan, document):
                    raise CaseConflictError("case_conflict")
                logger.info(
                    "Synthetic case replay accepted case_id=%s phone_suffix=%s",
                    existing_case.id,
                    phone_e164[-4:],
                )
                return CreateCaseResult(existing_case, existing_plan, False)

        if existing_case is None and existing_plan is not None:
            raise CaseConflictError("case_conflict")

        patient_case = existing_case or PatientCase(
            id=case_input.case_id,
            patient_alias=case_input.patient_alias,
            phone_e164=phone_e164,
            dialect_code=case_input.dialect_code,
            expected_box_count=case_input.expected_box_count,
            status="active",
        )
        approved_plan = ApprovedPlan(
            id=plan_input.plan_id,
            case_id=case_input.case_id,
            version=plan_input.version,
            source_hash=plan_input.source.source_hash,
            approved_by=plan_input.approved_by,
            approved_at=plan_input.approved_at,
            clinical_facts=plan_input.clinical_facts.model_dump(mode="json", by_alias=True),
        )
        try:
            if existing_case is None:
                self.session.add(patient_case)
                # No ORM relationship links these two immutable records, so
                # explicitly persist the FK parent before inserting the plan.
                self.session.flush()
            self.session.add(approved_plan)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise CaseConflictError("case_conflict") from exc

        logger.info(
            "Synthetic case created case_id=%s phone_suffix=%s",
            patient_case.id,
            phone_e164[-4:],
        )
        return CreateCaseResult(patient_case, approved_plan, True)

    def get_timeline(self, case_id: str) -> list[dict[str, Any]]:
        patient_case = self.session.get(PatientCase, case_id)
        if patient_case is None:
            raise CaseNotFoundError(case_id)
        plans = self.session.scalars(
            select(ApprovedPlan)
            .where(ApprovedPlan.case_id == case_id)
            .order_by(ApprovedPlan.created_at, ApprovedPlan.version)
        ).all()
        entries: list[dict[str, Any]] = [
            {
                "type": "case_created",
                "occurred_at": patient_case.created_at,
                "details": {"status": patient_case.status},
            }
        ]
        entries.extend(
            {
                "type": "approved_plan_loaded",
                "occurred_at": plan.created_at,
                "details": {"planId": plan.id, "version": plan.version},
            }
            for plan in plans
        )
        plan_ids = [plan.id for plan in plans]
        if plan_ids:
            artifacts = self.session.scalars(
                select(VoiceArtifact)
                .where(VoiceArtifact.plan_id.in_(plan_ids))
                .order_by(VoiceArtifact.created_at)
            ).all()
            for artifact in artifacts:
                entries.append(
                    {
                        "type": "voice_script_generated",
                        "occurred_at": artifact.created_at,
                        "details": {
                            "artifactId": artifact.id,
                            "approvalStatus": artifact.approval_status,
                        },
                    }
                )
                if artifact.approved_at is not None:
                    entries.append(
                        {
                            "type": "voice_script_approved",
                            "occurred_at": artifact.approved_at,
                            "details": {
                                "artifactId": artifact.id,
                                "approvedBy": artifact.approved_by or "unknown",
                            },
                        }
                    )

        messages = self.session.scalars(
            select(MessageLog)
            .where(MessageLog.case_id == case_id)
            .order_by(MessageLog.created_at, MessageLog.id)
        ).all()
        for message in messages:
            details: dict[str, str | int] = {
                "status": message.processing_status,
                "step": message.outbound_step or "inbound",
            }
            if message.delivery_status is not None:
                details["deliveryStatus"] = message.delivery_status
            choice = message.normalized_payload.get("buttonPayload")
            if isinstance(choice, str) and choice:
                details["choice"] = choice
            entries.append(
                {
                    "type": f"whatsapp_{message.direction}_{message.message_type}",
                    "occurred_at": message.created_at,
                    "details": details,
                }
            )

        media = self.session.scalars(
            select(InboundMedia)
            .where(InboundMedia.case_id == case_id)
            .order_by(InboundMedia.received_at, InboundMedia.id)
        ).all()
        entries.extend(
            {
                "type": "medicine_photo_stored",
                "occurred_at": item.received_at,
                "details": {"mediaId": item.id, "status": item.processing_status},
            }
            for item in media
        )

        events = self.session.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.case_id == case_id)
            .order_by(WorkflowEvent.created_at, WorkflowEvent.sequence)
        ).all()
        for event in events:
            entries.append(
                {
                    "type": "workflow_event_created",
                    "occurred_at": event.created_at,
                    "details": {
                        "eventId": event.event_id,
                        "eventType": event.event_type,
                    },
                }
            )
            outcome = self.session.scalar(
                select(ReviewOutcome).where(ReviewOutcome.workflow_event_sequence == event.sequence)
            )
            if outcome is not None:
                entries.append(
                    {
                        "type": "review_outcome_recorded",
                        "occurred_at": outcome.created_at,
                        "details": {
                            "outcomeId": outcome.id,
                            "outcome": outcome.outcome,
                        },
                    }
                )
        return entries

    @staticmethod
    def _same_case(stored: PatientCase, document: ApprovedPlanDocument, phone_e164: str) -> bool:
        requested = document.case
        return (
            stored.patient_alias == requested.patient_alias
            and stored.phone_e164 == phone_e164
            and stored.dialect_code == requested.dialect_code
            and stored.expected_box_count == requested.expected_box_count
        )

    @staticmethod
    def _same_plan(stored: ApprovedPlan, document: ApprovedPlanDocument) -> bool:
        requested = document.approved_plan
        facts = requested.clinical_facts.model_dump(mode="json", by_alias=True)
        stored_approved_at = stored.approved_at
        if stored_approved_at.tzinfo is None:
            stored_approved_at = stored_approved_at.replace(tzinfo=UTC)
        return (
            stored.id == requested.plan_id
            and stored.source_hash == requested.source.source_hash
            and stored.approved_by == requested.approved_by
            and stored_approved_at == requested.approved_at
            and stored.clinical_facts == facts
        )
