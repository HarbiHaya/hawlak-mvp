"""Medicine-box photos: who may send them, what the label check does, and what people see."""

from hashlib import sha256

import pytest

from app.models import Alert, InboundMedia
from app.schemas.care_journey import CareJourneyCreate
from app.services.care_journey_service import CareJourneyService
from app.services.inbound_workflow import InboundWorkflow
from app.services.medicine_photos import (
    PHOTO_REPLIES,
    LabelReading,
    compare_reading,
)
from app.services.object_storage import StoredObject
from app.services.whatsapp_client import DownloadedMedia

PATIENT = "+966500000000"
CAREGIVER = "+966522222222"
# Fictional medicines only.
MEDICATIONS = [
    {
        "medicationId": "SYN-MED-001",
        "displayName": "Zentorin 5 mg",
        "doseInstruction": "One tablet every morning",
        "dispensed": True,
        "reminderEnabled": False,
        "reminderScript": "",
    },
    {
        "medicationId": "SYN-MED-002",
        "displayName": "Calvexa 500 mg",
        "doseInstruction": "One tablet with dinner",
        "dispensed": True,
        "reminderEnabled": False,
        "reminderScript": "",
    },
]


def intake(caregiver: str | None = CAREGIVER, language: str = "ar") -> dict:
    return {
        "caseId": "case_photo_01",
        "patientName": "Synthetic Patient One",
        "phoneE164": PATIENT,
        "caregiverPhoneE164": caregiver,
        "languageCode": language,
        "dialectCode": "ar-SA-najdi",
        "sourceDocument": {"objectKey": "cases/case_photo_01/media/d.pdf", "filename": "d.pdf"},
        "dischargeVoiceNote": {"enabled": False, "script": ""},
        "medications": MEDICATIONS,
        "callPlan": {
            "enabled": False,
            "openingScript": "",
            "questions": [],
            "completionScript": "",
            "transferScript": "",
            "transferTarget": "",
            "responderPhoneE164": "",
        },
    }


class FakeStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def store_case_media(self, *, case_id, content, content_type, source_media_id):
        key = f"cases/{case_id}/media/{source_media_id}.jpg"
        self.objects[key] = content
        return StoredObject(key, len(content), sha256(content).hexdigest(), "e", content_type)


class FakeWhatsApp:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def download_image(self, media_id: str):
        return DownloadedMedia(f"image:{media_id}".encode(), "image/jpeg")

    async def send_text(self, to: str, text: str):
        self.sent.append((to, text))
        return f"wamid.sent.{len(self.sent)}"


class FakeReader:
    """Reads the label the test says is on the box behind each media ID."""

    def __init__(self, labels: dict[str, LabelReading]):
        self.labels = labels
        self.seen: list[bytes] = []

    async def read(self, content: bytes, mime_type: str) -> LabelReading:
        self.seen.append(content)
        return self.labels[content.decode().split(":", 1)[1]]


def readable(name: str, strength: str | None = None) -> LabelReading:
    return LabelReading(readable=True, name=name, strength=strength, form="tablet")


UNREADABLE = LabelReading(readable=False, name=None, strength=None, form=None)


def seed(db_session, **kwargs) -> None:
    CareJourneyService(db_session).intake(CareJourneyCreate.model_validate(intake(**kwargs)))


async def send_photo(workflow, number: int, sender: str = PATIENT) -> None:
    await workflow.ingest_message(
        wa_message_id=f"wamid.photo.{number}",
        sender=sender.lstrip("+"),
        message_type="image",
        media_id=f"m{number}",
        mime_type="image/jpeg",
    )


def test_label_matching_is_done_by_code_against_the_plan():
    assert compare_reading(readable("ZENTORIN", "5mg"), MEDICATIONS) == ("matched", "SYN-MED-001")
    assert compare_reading(readable("Zentorin", "10 mg"), MEDICATIONS) == (
        "strength_mismatch",
        "SYN-MED-001",
    )
    assert compare_reading(readable("Brovalin", "5 mg"), MEDICATIONS) == ("not_in_plan", None)
    assert compare_reading(UNREADABLE, MEDICATIONS) == ("unreadable", None)
    assert compare_reading(None, MEDICATIONS) == ("not_checked", None)
    # Arabic-Indic digits on a box read the same as Latin ones.
    assert compare_reading(readable("Calvexa", "٥٠٠ mg"), MEDICATIONS) == (
        "matched",
        "SYN-MED-002",
    )


@pytest.mark.anyio
async def test_caregiver_phone_can_send_photos_and_gets_the_fixed_replies(db_session):
    seed(db_session)
    whatsapp = FakeWhatsApp()
    reader = FakeReader({"m1": readable("Zentorin", "5 mg"), "m2": readable("Calvexa", "500mg")})
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp, reader)

    await send_photo(workflow, 1, sender=CAREGIVER)
    await send_photo(workflow, 2, sender=PATIENT)

    photos = db_session.query(InboundMedia).order_by(InboundMedia.received_at).all()
    assert [p.sender_role for p in photos] == ["caregiver", "patient"]
    assert [p.check_status for p in photos] == ["matched", "matched"]
    assert [p.medication_id for p in photos] == ["SYN-MED-001", "SYN-MED-002"]
    assert whatsapp.sent == [
        (CAREGIVER, PHOTO_REPLIES["ar"]["received"].format(n=1, total=2)),
        (PATIENT, PHOTO_REPLIES["ar"]["complete"]),
    ]
    alerts = db_session.query(Alert).all()
    assert [(a.type, a.severity) for a in alerts] == [("medicine_photos_ready", "low")]


@pytest.mark.anyio
async def test_a_mismatch_alerts_a_person_and_tells_the_sender_nothing_clinical(db_session):
    seed(db_session)
    whatsapp = FakeWhatsApp()
    reader = FakeReader({"m1": readable("Zentorin", "10 mg"), "m2": readable("Brovalin")})
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp, reader)

    await send_photo(workflow, 1)
    await send_photo(workflow, 2)

    alerts = db_session.query(Alert).filter_by(type="medicine_photo_mismatch").all()
    assert len(alerts) == 2
    assert {a.severity for a in alerts} == {"high"}
    for _, text in whatsapp.sent:
        assert "Zentorin" not in text and "Brovalin" not in text and "10" not in text


@pytest.mark.anyio
async def test_an_unreadable_photo_asks_for_a_retake_and_is_not_counted(db_session):
    seed(db_session, language="en")
    whatsapp = FakeWhatsApp()
    reader = FakeReader({"m1": UNREADABLE, "m2": readable("Zentorin", "5 mg")})
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp, reader)

    await send_photo(workflow, 1)
    await send_photo(workflow, 2)

    assert whatsapp.sent == [
        (PATIENT, PHOTO_REPLIES["en"]["retake"]),
        (PATIENT, PHOTO_REPLIES["en"]["received"].format(n=1, total=2)),
    ]
    assert db_session.query(Alert).count() == 0


@pytest.mark.anyio
async def test_without_a_reader_photos_wait_for_a_person(db_session):
    seed(db_session)
    whatsapp = FakeWhatsApp()
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp)

    await send_photo(workflow, 1)

    assert db_session.query(InboundMedia).one().check_status == "not_checked"
    assert whatsapp.sent == [(PATIENT, PHOTO_REPLIES["ar"]["received"].format(n=1, total=2))]


@pytest.mark.anyio
async def test_a_number_that_is_neither_patient_nor_caregiver_is_ignored(db_session):
    seed(db_session, caregiver=None)
    whatsapp = FakeWhatsApp()
    reader = FakeReader({})
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp, reader)

    await send_photo(workflow, 1, sender=CAREGIVER)

    assert db_session.query(InboundMedia).count() == 0
    assert whatsapp.sent == [] and reader.seen == []


def test_caregiver_phone_must_differ_from_the_patient_phone():
    with pytest.raises(ValueError):
        CareJourneyCreate.model_validate(intake(caregiver=PATIENT))


@pytest.mark.anyio
async def test_reviewer_sees_photos_and_confirming_resolves_the_alert(
    client, internal_auth_headers, db_session
):
    seed(db_session)
    reader = FakeReader({"m1": readable("Zentorin", "10 mg")})
    await send_photo(InboundWorkflow(db_session, FakeStorage(), FakeWhatsApp(), reader), 1)

    detail = client.get("/internal/workspace/cases/case_photo_01", headers=internal_auth_headers)
    [photo] = detail.json()["medicinePhotos"]
    assert photo["sender"] == "patient"
    assert photo["checkStatus"] == "strength_mismatch"
    assert photo["medicationId"] == "SYN-MED-001"
    assert photo["reading"] == {"name": "Zentorin", "strength": "10 mg", "form": "tablet"}
    assert photo["objectKey"].startswith("cases/case_photo_01/")
    assert photo["reviewStatus"] is None

    caregiver = client.get("/internal/caregiver/cases/case_photo_01", headers=internal_auth_headers)
    assert [m["photoStatus"] for m in caregiver.json()["medications"]] == [
        "needs_attention",
        "missing",
    ]

    reviewed = client.post(
        f"/internal/workspace/cases/case_photo_01/photos/{photo['id']}/review",
        json={"decision": "confirmed", "reviewedBy": "SYN-PHARMACIST-01"},
        headers=internal_auth_headers,
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["reviewStatus"] == "confirmed"
    assert db_session.query(Alert).filter_by(status="open").count() == 0

    caregiver = client.get("/internal/caregiver/cases/case_photo_01", headers=internal_auth_headers)
    assert caregiver.json()["medications"][0]["photoStatus"] == "confirmed"
    assert CAREGIVER not in str(caregiver.json())


def test_reviewing_a_photo_from_another_case_is_not_found(client, internal_auth_headers):
    response = client.post(
        "/internal/workspace/cases/case_photo_01/photos/nope/review",
        json={"decision": "confirmed", "reviewedBy": "SYN-PHARMACIST-01"},
        headers=internal_auth_headers,
    )
    assert response.status_code == 404
