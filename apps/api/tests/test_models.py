from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    ApprovedPlan,
    InboundMedia,
    MessageLog,
    PatientCase,
    ReviewOutcome,
    WorkflowEvent,
)


def add_case(db_session, *, case_id: str = "case_01") -> PatientCase:
    case = PatientCase(
        id=case_id,
        patient_alias="محمد عبدالله السالم",
        phone_e164="+966500000000",
        dialect_code="ar-SA-najdi",
        expected_box_count=3,
        status="active",
    )
    db_session.add(case)
    db_session.commit()
    return case


def add_plan(db_session, case: PatientCase) -> ApprovedPlan:
    plan = ApprovedPlan(
        id="plan_01",
        case_id=case.id,
        version=1,
        source_hash="sha256:fixture",
        approved_by="SYN-CLINICIAN-01",
        approved_at=datetime.now(UTC),
        clinical_facts={"emergencyNumber": "997"},
    )
    db_session.add(plan)
    db_session.commit()
    return plan


def test_plan_case_and_version_are_unique(db_session):
    case = add_case(db_session)
    add_plan(db_session, case)
    db_session.add(
        ApprovedPlan(
            id="plan_02",
            case_id=case.id,
            version=1,
            source_hash="sha256:other",
            approved_by="SYN-CLINICIAN-02",
            approved_at=datetime.now(UTC),
            clinical_facts={},
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_message_media_and_outbound_step_uniqueness(db_session):
    case = add_case(db_session)
    first = MessageLog(
        id="message_01",
        case_id=case.id,
        wa_message_id="wamid.01",
        direction="inbound",
        message_type="image",
        processing_status="received",
        normalized_payload={},
    )
    db_session.add(first)
    db_session.commit()
    db_session.add(
        InboundMedia(
            id="media_01",
            case_id=case.id,
            message_log_id=first.id,
            meta_media_id="meta-media-01",
            mime_type="image/jpeg",
            processing_status="stored",
        )
    )
    db_session.commit()

    db_session.add(
        InboundMedia(
            id="media_02",
            case_id=case.id,
            message_log_id=first.id,
            meta_media_id="meta-media-02",
            mime_type="image/jpeg",
            processing_status="stored",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
    db_session.add_all(
        [
            MessageLog(
                id="outbound_01",
                case_id=case.id,
                wa_message_id="wamid.out.01",
                direction="outbound",
                message_type="text",
                processing_status="sent",
                normalized_payload={},
                outbound_step="disclosure",
            ),
            MessageLog(
                id="outbound_02",
                case_id=case.id,
                wa_message_id="wamid.out.02",
                direction="outbound",
                message_type="text",
                processing_status="sent",
                normalized_payload={},
                outbound_step="disclosure",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_event_and_review_outcome_idempotency_keys_are_unique(db_session):
    case = add_case(db_session)
    event = WorkflowEvent(
        event_id="evt_01",
        case_id=case.id,
        event_type="pharmacist_review_requested",
        event_version=1,
        payload={},
        idempotency_key="case_01:pharmacist_review_requested:v1",
    )
    db_session.add(event)
    db_session.commit()
    db_session.add(
        WorkflowEvent(
            event_id="evt_02",
            case_id=case.id,
            event_type="pharmacist_review_requested",
            event_version=1,
            payload={},
            idempotency_key=event.idempotency_key,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
    db_session.add(
        ReviewOutcome(
            id="outcome_01",
            workflow_event_sequence=event.sequence,
            outcome="matched",
            reviewer_id="demo-pharmacist-01",
            idempotency_key="review-action-01",
        )
    )
    db_session.commit()
    db_session.add(
        ReviewOutcome(
            id="outcome_02",
            workflow_event_sequence=event.sequence,
            outcome="unclear_photo",
            reviewer_id="demo-pharmacist-01",
            idempotency_key="review-action-01",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
