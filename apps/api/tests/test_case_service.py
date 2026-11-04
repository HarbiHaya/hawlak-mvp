from copy import deepcopy

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ApprovedPlan, PatientCase
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
