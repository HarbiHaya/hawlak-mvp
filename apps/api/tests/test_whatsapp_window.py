"""The WhatsApp opener: free-form messages wait until the patient has written in 24 hours."""

from datetime import timedelta

import pytest
from test_care_journey import intake_body

from app.models import Alert, DeliveryRun, MessageLog, utc_now
from app.services.care_journey_service import CareJourneyService
from app.services.journey_delivery import JourneyDeliveryOrchestrator, window_open

CASE = "case_poc_01"


class FakeAdapter:
    def __init__(self, template_kinds=frozenset()):
        self.template_kinds = frozenset(template_kinds)
        self.sent: list[tuple[str, str, bool]] = []

    async def deliver(self, payload) -> str:
        self.sent.append((payload.kind, payload.content_ref, payload.window_open))
        return f"wamid.{len(self.sent)}"


def approved_case(client, internal_auth_headers, db_session, opener=True):
    client.post("/internal/workspace/cases", json=intake_body(), headers=internal_auth_headers)
    CareJourneyService(db_session).approve(CASE, "SYN-INTEGRATED-CARE-01", "key-1", opener=opener)


def runs(db_session, kind):
    return db_session.query(DeliveryRun).filter_by(case_id=CASE, kind=kind).all()


def patient_writes(db_session, role="patient", at=None):
    db_session.add(
        MessageLog(
            case_id=CASE,
            wa_message_id=f"wamid.in.{role}",
            direction="inbound",
            message_type="button",
            processing_status="processed",
            normalized_payload={"senderRole": role},
            created_at=at or utc_now(),
        )
    )
    db_session.commit()


def age_runs(db_session, hours):
    for run in db_session.query(DeliveryRun).filter_by(case_id=CASE):
        run.scheduled_at = run.scheduled_at - timedelta(hours=hours)
    db_session.commit()


def test_approval_creates_two_openers_when_a_template_is_set(
    client, internal_auth_headers, db_session
):
    approved_case(client, internal_auth_headers, db_session)

    openers = sorted(runs(db_session, "whatsapp_opener"), key=lambda r: r.scheduled_at)
    assert [r.content_ref for r in openers] == ["opener", "opener:2"]
    assert openers[1].scheduled_at - openers[0].scheduled_at == timedelta(hours=4)


def test_approval_creates_no_opener_without_a_template(client, internal_auth_headers, db_session):
    approved_case(client, internal_auth_headers, db_session, opener=False)

    assert runs(db_session, "whatsapp_opener") == []


@pytest.mark.anyio
async def test_voice_note_waits_until_the_patient_writes(client, internal_auth_headers, db_session):
    approved_case(client, internal_auth_headers, db_session)
    adapter = FakeAdapter()

    await JourneyDeliveryOrchestrator(db_session, adapter).dispatch_due(CASE)

    assert runs(db_session, "discharge_voice_note")[0].status == "pending"
    assert ("whatsapp_opener", "opener", False) in adapter.sent

    patient_writes(db_session)
    await JourneyDeliveryOrchestrator(db_session, adapter).dispatch_due(CASE)

    assert runs(db_session, "discharge_voice_note")[0].status == "sent"
    assert runs(db_session, "photo_request")[0].status == "sent"


@pytest.mark.anyio
async def test_photo_request_with_a_template_does_not_wait(
    client, internal_auth_headers, db_session
):
    approved_case(client, internal_auth_headers, db_session)

    await JourneyDeliveryOrchestrator(db_session, FakeAdapter({"photo_request"})).dispatch_due(CASE)

    assert runs(db_session, "photo_request")[0].status == "sent"
    assert runs(db_session, "discharge_voice_note")[0].status == "pending"


@pytest.mark.anyio
async def test_second_opener_is_skipped_once_the_window_is_open(
    client, internal_auth_headers, db_session
):
    approved_case(client, internal_auth_headers, db_session)
    age_runs(db_session, 5)
    patient_writes(db_session)
    adapter = FakeAdapter()

    await JourneyDeliveryOrchestrator(db_session, adapter).dispatch_due(CASE)

    second = next(r for r in runs(db_session, "whatsapp_opener") if r.content_ref == "opener:2")
    assert second.status == "completed"
    assert ("whatsapp_opener", "opener:2", True) not in adapter.sent


@pytest.mark.anyio
async def test_caregiver_message_does_not_open_the_window(
    client, internal_auth_headers, db_session
):
    approved_case(client, internal_auth_headers, db_session)
    patient_writes(db_session, role="caregiver")

    await JourneyDeliveryOrchestrator(db_session, FakeAdapter()).dispatch_due(CASE)

    assert window_open(db_session, CASE, utc_now()) is False
    assert runs(db_session, "discharge_voice_note")[0].status == "pending"


def test_a_message_older_than_24_hours_does_not_open_the_window(
    client, internal_auth_headers, db_session
):
    approved_case(client, internal_auth_headers, db_session)
    patient_writes(db_session, at=utc_now() - timedelta(hours=25))

    assert window_open(db_session, CASE, utc_now()) is False


@pytest.mark.anyio
async def test_patient_not_reached_alert_after_24_hours(client, internal_auth_headers, db_session):
    approved_case(client, internal_auth_headers, db_session)
    age_runs(db_session, 25)

    for _ in range(2):
        await JourneyDeliveryOrchestrator(db_session, FakeAdapter()).dispatch_due(CASE)

    alerts = db_session.query(Alert).filter_by(case_id=CASE, type="patient_not_reached").all()
    assert [a.severity for a in alerts] == ["high"]


@pytest.mark.anyio
async def test_reminder_waits_for_the_window_unless_a_reminder_template_is_set(
    client, internal_auth_headers, db_session
):
    approved_case(client, internal_auth_headers, db_session)

    await JourneyDeliveryOrchestrator(db_session, FakeAdapter()).dispatch_due(CASE)
    assert runs(db_session, "medication_reminder")[0].status == "pending"

    adapter = FakeAdapter({"medication_reminder"})
    await JourneyDeliveryOrchestrator(db_session, adapter).dispatch_due(CASE)
    assert runs(db_session, "medication_reminder")[0].status == "sent"
    assert ("medication_reminder", runs(db_session, "medication_reminder")[0].content_ref,
            False) in adapter.sent  # fmt: skip
