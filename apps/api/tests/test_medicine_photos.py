"""Medicine-box photos: Hawlak asks for each approved medicine in turn, links the photo to that
medicine by slot (never by AI guess), and the label check only confirms that one box."""

from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

import pytest

from app.models import Alert, DeliveryRun, InboundMedia
from app.schemas.care_journey import CareJourneyCreate
from app.services.care_journey_service import CareJourneyService
from app.services.inbound_workflow import InboundWorkflow
from app.services.journey_delivery import (
    JourneyDeliveryOrchestrator,
    JourneyDeliveryPayload,
    LiveJourneyDeliveryAdapter,
)
from app.services.medicine_photos import (
    PHOTO_REPLIES,
    LabelReading,
    compare_reading,
    photo_request_text,
)
from app.services.object_storage import StoredObject
from app.services.whatsapp_client import DownloadedMedia

PATIENT = "+966500000000"
CAREGIVER = "+966522222222"
# Fictional medicines only.
ZENTORIN = {
    "medicationId": "SYN-MED-001",
    "displayName": "Zentorin 5 mg",
    "doseInstruction": "One tablet every morning",
    "dispensed": True,
    "reminderEnabled": True,
    "reminderScript": "Time for your morning tablet.",
}
CALVEXA = {
    "medicationId": "SYN-MED-002",
    "displayName": "Calvexa 500 mg",
    "doseInstruction": "One tablet with dinner",
    "dispensed": True,
    "reminderEnabled": False,
    "reminderScript": "",
}


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
        "medications": [ZENTORIN, CALVEXA],
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
    def __init__(self, images: dict[str, bytes] | None = None):
        self.sent: list[tuple[str, str]] = []
        self.images = images or {}

    async def download_image(self, media_id: str):
        content = self.images.get(media_id, f"image:{media_id}".encode())
        return DownloadedMedia(content, "image/jpeg")

    async def send_text(self, to: str, text: str):
        self.sent.append((to, text))
        return f"wamid.sent.{len(self.sent)}"


class FakeReader:
    """Reads the label the test says is on the box behind each media ID."""

    def __init__(self, labels: dict[str, LabelReading]):
        self.labels = labels
        self.calls = 0

    async def read(self, content: bytes, mime_type: str) -> LabelReading:
        self.calls += 1
        return self.labels[content.decode().split(":", 1)[1]]


def readable(name: str, strength: str | None = None) -> LabelReading:
    return LabelReading(readable=True, name=name, strength=strength, form="tablet")


UNREADABLE = LabelReading(readable=False, name=None, strength=None, form=None)
AR = PHOTO_REPLIES["ar"]


def seed(db_session, **kwargs) -> None:
    CareJourneyService(db_session).intake(CareJourneyCreate.model_validate(intake(**kwargs)))


async def send_photo(workflow, number: int, sender: str = PATIENT, media: str | None = None):
    await workflow.ingest_message(
        wa_message_id=f"wamid.photo.{number}",
        sender=sender.lstrip("+"),
        message_type="image",
        media_id=media or f"m{number}",
        mime_type="image/jpeg",
    )


def test_the_label_is_checked_against_the_one_expected_medicine():
    assert compare_reading(readable("ZENTORIN", "5mg"), ZENTORIN) == "matched"
    assert compare_reading(readable("Zentorin", "10 mg"), ZENTORIN) == "strength_mismatch"
    assert compare_reading(readable("Calvexa", "500 mg"), ZENTORIN) == "different_medicine"
    assert compare_reading(UNREADABLE, ZENTORIN) == "unreadable"
    assert compare_reading(None, ZENTORIN) == "not_checked"
    # Arabic-Indic digits on a box read the same as Latin ones.
    assert compare_reading(readable("Calvexa", "٥٠٠ mg"), CALVEXA) == "matched"


def test_the_first_request_names_the_first_approved_medicine():
    assert photo_request_text([ZENTORIN, CALVEXA], "ar") == AR["request"].format(
        n=1, total=2, name="Zentorin 5 mg"
    )
    assert photo_request_text([{**ZENTORIN, "dispensed": False}], "en") is None


@pytest.mark.anyio
async def test_photos_link_to_the_requested_medicine_by_slot(db_session):
    seed(db_session)
    whatsapp = FakeWhatsApp()
    # The second box is actually Zentorin again: still linked to Calvexa's slot, and flagged.
    reader = FakeReader({"m1": readable("Zentorin", "5 mg"), "m2": readable("Zentorin", "5 mg")})
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp, reader)

    await send_photo(workflow, 1, sender=CAREGIVER)
    await send_photo(workflow, 2)

    photos = db_session.query(InboundMedia).order_by(InboundMedia.received_at).all()
    assert [p.medication_id for p in photos] == ["SYN-MED-001", "SYN-MED-002"]
    assert [p.check_status for p in photos] == ["matched", "different_medicine"]
    assert [p.sender_role for p in photos] == ["caregiver", "patient"]
    assert whatsapp.sent == [
        (CAREGIVER, AR["next"].format(n=2, total=2, name="Calvexa 500 mg")),
        (PATIENT, AR["complete"]),
    ]
    assert {a.type for a in db_session.query(Alert)} == {
        "medicine_photo_mismatch",
        "medicine_photos_ready",
    }


@pytest.mark.anyio
async def test_an_unreadable_photo_keeps_the_slot_and_asks_again_by_name(db_session):
    seed(db_session, language="en")
    whatsapp = FakeWhatsApp()
    reader = FakeReader({"m1": UNREADABLE, "m2": readable("Zentorin", "5 mg")})
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp, reader)

    await send_photo(workflow, 1)
    await send_photo(workflow, 2)

    en = PHOTO_REPLIES["en"]
    assert whatsapp.sent == [
        (PATIENT, en["retake"].format(name="Zentorin 5 mg")),
        (PATIENT, en["next"].format(n=2, total=2, name="Calvexa 500 mg")),
    ]
    assert [p.medication_id for p in db_session.query(InboundMedia)] == ["SYN-MED-001"] * 2
    assert db_session.query(Alert).count() == 0


@pytest.mark.anyio
async def test_the_same_photo_sent_twice_is_read_once(db_session):
    seed(db_session)
    same = b"image:m1"
    reader = FakeReader({"m1": UNREADABLE})
    whatsapp = FakeWhatsApp({"a": same, "b": same})
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp, reader)

    await send_photo(workflow, 1, media="a")
    await send_photo(workflow, 2, media="b")

    assert reader.calls == 1
    assert [p.check_status for p in db_session.query(InboundMedia)] == ["unreadable"] * 2


@pytest.mark.anyio
async def test_without_a_reader_photos_still_link_and_wait_for_a_person(db_session):
    seed(db_session)
    whatsapp = FakeWhatsApp()
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp)

    await send_photo(workflow, 1)

    photo = db_session.query(InboundMedia).one()
    assert (photo.medication_id, photo.check_status) == ("SYN-MED-001", "not_checked")
    assert whatsapp.sent == [(PATIENT, AR["next"].format(n=2, total=2, name="Calvexa 500 mg"))]


@pytest.mark.anyio
async def test_a_number_that_is_neither_patient_nor_caregiver_is_ignored(db_session):
    seed(db_session, caregiver=None)
    whatsapp = FakeWhatsApp()
    reader = FakeReader({})
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp, reader)

    await send_photo(workflow, 1, sender=CAREGIVER)

    assert db_session.query(InboundMedia).count() == 0
    assert whatsapp.sent == [] and reader.calls == 0


def test_caregiver_phone_must_differ_from_the_patient_phone():
    with pytest.raises(ValueError):
        CareJourneyCreate.model_validate(intake(caregiver=PATIENT))


def approve(db_session) -> list[DeliveryRun]:
    service = CareJourneyService(db_session)
    service.check_eligibility("case_photo_01", "SYN-4471203")
    return service.approve("case_photo_01", "SYN-REVIEWER", "approve-photos")


def test_approval_needs_no_insurer_image_and_queues_the_photo_request(db_session):
    seed(db_session)

    runs = approve(db_session)

    assert [r.kind for r in runs].count("photo_request") == 1
    payload = JourneyDeliveryOrchestrator._payload(
        next(r for r in runs if r.kind == "photo_request"),
        *CareJourneyService(db_session)._get("case_photo_01"),
    )
    assert payload.text == AR["request"].format(n=1, total=2, name="Zentorin 5 mg")


@pytest.mark.anyio
async def test_a_matched_patient_photo_becomes_the_reminder_image(db_session):
    seed(db_session)
    runs = approve(db_session)
    reminder = next(r for r in runs if r.kind == "medication_reminder")
    journey, patient = CareJourneyService(db_session)._get("case_photo_01")

    assert JourneyDeliveryOrchestrator._payload(reminder, journey, patient).image_object_key is None

    reader = FakeReader({"m1": readable("Zentorin", "5 mg")})
    await send_photo(InboundWorkflow(db_session, FakeStorage(), FakeWhatsApp(), reader), 1)

    payload = JourneyDeliveryOrchestrator._payload(reminder, journey, patient)
    assert payload.image_object_key == "cases/case_photo_01/media/m1.jpg"


@pytest.mark.anyio
async def test_reviewer_confirms_a_flagged_photo_and_caregiver_sees_it(
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


def test_the_insurer_can_no_longer_upload_medicine_images(client, internal_auth_headers):
    response = client.post(
        "/internal/workspace/cases/case_photo_01/medication-images",
        content=b"\xff\xd8\xff synthetic",
        headers={**internal_auth_headers, "Content-Type": "image/jpeg", "X-Filename": "m.jpg"},
    )
    assert response.status_code in {404, 405}


class LiveFakes:
    def __init__(self):
        self.calls: list[tuple] = []

    async def render(self, script):
        return SimpleNamespace(audio=b"ogg")

    async def upload_audio(self, audio, filename):
        return "audio-id"

    async def send_audio(self, to, audio_id):
        self.calls.append(("audio", to))
        return "wamid.audio"

    async def send_text(self, to, text):
        self.calls.append(("text", to, text))
        return "wamid.text"


def live_adapter(fakes) -> LiveJourneyDeliveryAdapter:
    adapter = object.__new__(LiveJourneyDeliveryAdapter)
    adapter._whatsapp = adapter._renderer = fakes
    return adapter


def payload(kind: str, **values) -> JourneyDeliveryPayload:
    return JourneyDeliveryPayload(
        run_id="run-1",
        case_id="case_photo_01",
        kind=kind,
        content_ref="x",
        scheduled_at=datetime.now(UTC),
        phone_e164=PATIENT,
        approved_by="SYN-REVIEWER",
        **values,
    )


@pytest.mark.anyio
async def test_live_delivery_sends_the_photo_request_as_text():
    fakes = LiveFakes()
    ref = await live_adapter(fakes).deliver(payload("photo_request", text="Please photograph"))
    assert ref == "wamid.text"
    assert fakes.calls == [("text", PATIENT, "Please photograph")]


@pytest.mark.anyio
async def test_live_reminder_without_a_checked_photo_sends_the_voice_note_alone():
    fakes = LiveFakes()
    ref = await live_adapter(fakes).deliver(payload("medication_reminder", voice_script="Dose"))
    assert ref == "wamid.audio"
    assert fakes.calls == [("audio", PATIENT)]
