from copy import deepcopy

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ApprovedPlan, MessageLog, PatientCase
from app.schemas.approved_plan import ApprovedPlanDocument
from app.services.case_service import CaseConflictError, CaseService


def as_document(plan: dict) -> ApprovedPlanDocument:
    return ApprovedPlanDocument.model_validate(plan)


def test_first_load_and_exact_replay_are_idempotent(db_session, plan):
    service = CaseService(db_session)

    first = service.create_case(as_document(plan), "+966500000000")
    second = service.create_case(as_document(plan), "+966500000000")

    assert first.created is True
    assert second.created is False
    assert first.case.id == second.case.id == "case_01"
    assert db_session.query(PatientCase).count() == 1
    assert db_session.query(ApprovedPlan).count() == 1


def test_case_is_flushed_before_plan_when_foreign_keys_are_enforced(plan):
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            result = CaseService(session).create_case(as_document(plan), "+966500000000")
            assert result.created is True
            assert session.get(PatientCase, "case_01") is not None
            assert session.get(ApprovedPlan, "plan_01") is not None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.parametrize("field", ["sourceHash", "clinicalFacts"])
def test_changed_plan_content_conflicts_without_mutating_original(db_session, plan, field):
    service = CaseService(db_session)
    service.create_case(as_document(plan), "+966500000000")
    changed = deepcopy(plan)
    if field == "sourceHash":
        changed["approvedPlan"]["source"][field] = "sha256:changed"
    else:
        changed["approvedPlan"][field]["emergencyNumber"] = "998"

    with pytest.raises(CaseConflictError):
        service.create_case(as_document(changed), "+966500000000")

    stored = db_session.query(ApprovedPlan).one()
    assert stored.source_hash == plan["approvedPlan"]["source"]["sourceHash"]
    assert stored.clinical_facts["emergencyNumber"] == "997"


def test_case_creation_logs_only_the_phone_suffix(db_session, plan, caplog):
    phone = "+966500000000"

    CaseService(db_session).create_case(as_document(plan), phone)

    assert "phone_suffix=0000" in caplog.text
    assert phone not in caplog.text


def test_non_synthetic_documents_are_rejected(plan):
    changed = deepcopy(plan)
    changed["synthetic"] = False

    with pytest.raises(ValueError):
        as_document(changed)


def test_timeline_exposes_delivery_status_and_numeric_button_choice(db_session, plan):
    service = CaseService(db_session)
    service.create_case(as_document(plan), "+966500000000")
    db_session.add_all(
        [
            MessageLog(
                case_id="case_01",
                wa_message_id="MM-outbound",
                direction="outbound",
                message_type="audio",
                processing_status="sent",
                delivery_status="delivered",
                normalized_payload={},
                outbound_step="session_summary",
                idempotency_key="timeline-outbound",
            ),
            MessageLog(
                case_id="case_01",
                wa_message_id="MM-inbound",
                direction="inbound",
                message_type="button",
                processing_status="processed",
                normalized_payload={"buttonPayload": "taken"},
                idempotency_key="timeline-inbound",
            ),
        ]
    )
    db_session.commit()

    timeline = service.get_timeline("case_01")
    message_entries = [entry for entry in timeline if entry["type"].startswith("whatsapp_")]

    assert message_entries[0]["details"] == {
        "status": "sent",
        "step": "session_summary",
        "deliveryStatus": "delivered",
    }
    assert message_entries[1]["details"] == {
        "status": "processed",
        "step": "inbound",
        "choice": "taken",
    }
