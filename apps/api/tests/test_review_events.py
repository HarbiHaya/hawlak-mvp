from datetime import UTC, datetime

from app.main import app
from app.models import InboundMedia, MessageLog, PatientCase, WorkflowEvent
from app.services.object_storage import get_object_storage


class FakeReadStorage:
    def get_bytes(self, key: str) -> bytes:
        assert key == "cases/case_01/media/photo.jpg"
        return b"synthetic-photo"


def seed_review_event(db_session):
    case = PatientCase(
        id="case_01",
        patient_alias="محمد عبدالله السالم",
        phone_e164="+966500000000",
        dialect_code="ar-SA-najdi",
        expected_box_count=1,
        status="review_requested",
    )
    message = MessageLog(
        id="message_01",
        case_id="case_01",
        wa_message_id="wamid.photo",
        direction="inbound",
        message_type="image",
        processing_status="processed",
        normalized_payload={},
    )
    media = InboundMedia(
        id="media_01",
        case_id="case_01",
        message_log_id="message_01",
        meta_media_id="meta-photo",
        mime_type="image/jpeg",
        object_key="cases/case_01/media/photo.jpg",
        object_sha256="abc",
        processing_status="stored",
    )
    payload = {
        "eventId": "evt_01",
        "eventType": "pharmacist_review_requested",
        "eventVersion": 1,
        "idempotencyKey": "case_01:pharmacist_review_requested:v1",
        "occurredAt": datetime.now(UTC).isoformat(),
        "case": {
            "caseId": "case_01",
            "patientAlias": "محمد عبدالله السالم",
            "phoneE164Masked": "+9665*****000",
            "expectedBoxCount": 1,
            "receivedBoxCount": 1,
        },
        "approvedPlan": {"planId": "plan_01", "version": 1, "sourceHash": "sha256:test"},
        "medicinePhotos": [{"mediaId": "media_01", "objectKey": "cases/case_01/media/photo.jpg"}],
        "reviewReason": "expected_photo_count_reached",
    }
    event = WorkflowEvent(
        event_id="evt_01",
        case_id="case_01",
        event_type="pharmacist_review_requested",
        event_version=1,
        payload=payload,
        idempotency_key=payload["idempotencyKey"],
    )
    db_session.add_all([case, message, media, event])
    db_session.commit()


def test_polling_media_and_outcome_flow(client, internal_auth_headers, db_session):
    seed_review_event(db_session)
    app.dependency_overrides[get_object_storage] = lambda: FakeReadStorage()

    page = client.get("/internal/review-events", headers=internal_auth_headers)
    assert page.status_code == 200
    assert [item["eventId"] for item in page.json()["data"]] == ["evt_01"]
    assert page.json()["nextCursor"].startswith("event-sequence:")

    empty = client.get(
        "/internal/review-events",
        params={"after": page.json()["nextCursor"]},
        headers=internal_auth_headers,
    )
    assert empty.json() == {"data": [], "nextCursor": page.json()["nextCursor"]}

    media = client.get("/internal/media/media_01", headers=internal_auth_headers)
    assert media.status_code == 200
    assert media.content == b"synthetic-photo"
    assert media.headers["content-type"] == "image/jpeg"

    outcome_body = {
        "eventVersion": 1,
        "outcome": "matched",
        "reviewerId": "demo-pharmacist-01",
        "note": None,
    }
    headers = {**internal_auth_headers, "Idempotency-Key": "review-action-01"}
    created = client.post(
        "/internal/review-events/evt_01/outcomes", json=outcome_body, headers=headers
    )
    replay = client.post(
        "/internal/review-events/evt_01/outcomes", json=outcome_body, headers=headers
    )
    assert created.status_code == 201
    assert replay.status_code == 200
    assert created.json() == replay.json()

    reloaded_queue = client.get("/internal/review-events", headers=internal_auth_headers)
    assert reloaded_queue.json()["data"] == []


def test_review_routes_enforce_auth_cursor_and_conflicts(client, internal_auth_headers, db_session):
    seed_review_event(db_session)
    assert client.get("/internal/review-events").status_code == 401
    assert (
        client.get(
            "/internal/review-events", params={"after": "bad"}, headers=internal_auth_headers
        ).status_code
        == 400
    )

    first_headers = {**internal_auth_headers, "Idempotency-Key": "review-action-01"}
    first = {
        "eventVersion": 1,
        "outcome": "matched",
        "reviewerId": "reviewer-1",
    }
    assert (
        client.post(
            "/internal/review-events/evt_01/outcomes", json=first, headers=first_headers
        ).status_code
        == 201
    )
    changed = {**first, "outcome": "unclear_photo"}
    assert (
        client.post(
            "/internal/review-events/evt_01/outcomes", json=changed, headers=first_headers
        ).status_code
        == 409
    )
