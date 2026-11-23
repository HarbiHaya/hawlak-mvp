"""Medicine-box photos: Hawlak asks for each approved medicine in turn, links the photo to that
medicine by slot (never by AI guess), and the label check only confirms that one box."""

from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

import pytest

from app.models import Alert, DeliveryRun, InboundMedia
from app.schemas.care_journey import CareJourneyCreate
from app.services.care_journey_service import CareJourneyService
from app.services.inbound_workflow import InboundWorkflow, PhotoUploadRejected
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
    template_body,
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


def intake(
    caregiver: str | None = CAREGIVER, language: str = "ar", medications: list | None = None
) -> dict:
    return {
        "caseId": "case_photo_01",
        "patientName": "Synthetic Patient One",
        "phoneE164": PATIENT,
        "caregiverPhoneE164": caregiver,
        "languageCode": language,
        "dialectCode": "ar-SA-najdi",
        "sourceDocument": {"objectKey": "cases/case_photo_01/media/d.pdf", "filename": "d.pdf"},
        "dischargeVoiceNote": {"enabled": False, "script": ""},
        "medications": medications or [ZENTORIN, CALVEXA],
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
async def test_a_box_sent_out_of_order_links_to_its_own_waiting_medicine(db_session):
    seed(db_session)
    whatsapp = FakeWhatsApp()
    # Asked for Zentorin first, the patient sends Calvexa first.
    reader = FakeReader({"m1": readable("Calvexa", "500 mg"), "m2": readable("Zentorin", "5 mg")})
    workflow = InboundWorkflow(db_session, FakeStorage(), whatsapp, reader)

    await send_photo(workflow, 1)
    await send_photo(workflow, 2)

    photos = db_session.query(InboundMedia).order_by(InboundMedia.received_at).all()
    assert [p.medication_id for p in photos] == ["SYN-MED-002", "SYN-MED-001"]
    assert [p.check_status for p in photos] == ["matched", "matched"]
    assert whatsapp.sent == [
        (PATIENT, AR["next"].format(n=1, total=2, name="Zentorin 5 mg")),
        (PATIENT, AR["complete"]),
    ]
    assert {a.type for a in db_session.query(Alert)} == {"medicine_photos_ready"}


@pytest.mark.anyio
async def test_a_box_that_fits_two_waiting_medicines_stays_on_the_requested_slot(db_session):
    twin = {**CALVEXA, "medicationId": "SYN-MED-003"}
    seed(db_session, medications=[ZENTORIN, CALVEXA, twin])
    reader = FakeReader({"m1": readable("Calvexa", "500 mg")})
    workflow = InboundWorkflow(db_session, FakeStorage(), FakeWhatsApp(), reader)

    await send_photo(workflow, 1)

    photo = db_session.query(InboundMedia).one()
    assert (photo.medication_id, photo.check_status) == ("SYN-MED-001", "different_medicine")
    assert {a.type for a in db_session.query(Alert)} == {"medicine_photo_mismatch"}


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
    # The same three values fill the WhatsApp template when one is configured.
    assert (payload.template_values, payload.language) == (("1", "2", "Zentorin 5 mg"), "ar")


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


JPEG = b"\xff\xd8\xff synthetic box photo"


def upload_workflow(db_session, reader=None, whatsapp=None) -> InboundWorkflow:
    return InboundWorkflow(db_session, FakeStorage(), whatsapp or FakeWhatsApp(), reader)


class BoxReader:
    """Reads the same label whatever the bytes are."""

    def __init__(self, label: LabelReading):
        self.label = label

    async def read(self, content: bytes, mime_type: str) -> LabelReading:
        return self.label


@pytest.mark.anyio
async def test_the_caregiver_uploads_a_photo_for_a_medicine_the_patient_did_not_send(db_session):
    seed(db_session)
    approve(db_session)
    whatsapp = FakeWhatsApp()
    workflow = upload_workflow(db_session, BoxReader(readable("Calvexa", "500 mg")), whatsapp)

    # The caregiver picks the medicine in the app, so the photo goes to that medicine.
    result = await workflow.ingest_caregiver_upload(
        case_id="case_photo_01", medication_id="SYN-MED-002", content=JPEG, mime_type="image/jpeg"
    )

    photo = db_session.query(InboundMedia).one()
    assert result == "received"
    assert (photo.medication_id, photo.check_status, photo.sender_role) == (
        "SYN-MED-002",
        "matched",
        "caregiver",
    )
    assert whatsapp.sent == []  # the app shows the result; nothing goes out on WhatsApp
    view = CareJourneyService(db_session).caregiver("case_photo_01")
    assert [(m["photoStatus"], m["canUploadPhoto"]) for m in view["medications"]] == [
        ("missing", True),
        ("received", False),
    ]
    # A photo on WhatsApp now fills the box that is still waiting.
    await send_photo(
        upload_workflow(db_session, FakeReader({"m1": readable("Zentorin", "5 mg")})), 1
    )
    assert {a.type for a in db_session.query(Alert)} == {"medicine_photos_ready"}


@pytest.mark.anyio
async def test_an_unclear_upload_can_be_sent_again_and_a_mismatch_alerts_a_person(db_session):
    seed(db_session)
    approve(db_session)
    upload = {"case_id": "case_photo_01", "medication_id": "SYN-MED-001", "mime_type": "image/jpeg"}

    unclear = await upload_workflow(db_session, BoxReader(UNREADABLE)).ingest_caregiver_upload(
        content=JPEG, **upload
    )
    wrong = await upload_workflow(
        db_session, BoxReader(readable("Calvexa", "500 mg"))
    ).ingest_caregiver_upload(content=JPEG + b"2", **upload)

    # The caregiver chose the medicine, so a wrong box is flagged, not moved to another one.
    assert (unclear, wrong) == ("unclear", "received")
    assert [
        p.check_status for p in db_session.query(InboundMedia).order_by(InboundMedia.received_at)
    ] == [
        "unreadable",
        "different_medicine",
    ]
    assert {a.type for a in db_session.query(Alert)} == {"medicine_photo_mismatch"}


@pytest.mark.anyio
async def test_caregiver_upload_is_refused_when_it_is_not_needed_or_not_allowed(db_session):
    upload = {"case_id": "case_photo_01", "content": JPEG, "mime_type": "image/jpeg"}
    seed(db_session)
    workflow = upload_workflow(db_session, BoxReader(readable("Zentorin", "5 mg")))

    with pytest.raises(PhotoUploadRejected, match="journey_not_approved"):
        await workflow.ingest_caregiver_upload(medication_id="SYN-MED-001", **upload)
    approve(db_session)
    with pytest.raises(LookupError):
        await workflow.ingest_caregiver_upload(medication_id="SYN-MED-404", **upload)
    await workflow.ingest_caregiver_upload(medication_id="SYN-MED-001", **upload)
    with pytest.raises(PhotoUploadRejected, match="photo_already_received"):
        await workflow.ingest_caregiver_upload(medication_id="SYN-MED-001", **upload)


@pytest.mark.anyio
async def test_no_upload_without_a_caregiver_registered_at_intake(db_session):
    seed(db_session, caregiver=None)
    approve(db_session)

    with pytest.raises(PhotoUploadRejected, match="caregiver_not_registered"):
        await upload_workflow(db_session).ingest_caregiver_upload(
            case_id="case_photo_01",
            medication_id="SYN-MED-001",
            content=JPEG,
            mime_type="image/jpeg",
        )
    view = CareJourneyService(db_session).caregiver("case_photo_01")
    assert [m["canUploadPhoto"] for m in view["medications"]] == [False, False]


def test_the_upload_route_takes_images_only_and_never_from_the_insurer(client, db_session):
    from app.services.object_storage import get_object_storage

    def session_headers(username: str) -> dict[str, str]:
        body = {"username": username, "password": "synthetic-demo-password"}
        token = client.post("/auth/login", json=body).json()["accessToken"]
        return {"Authorization": f"Bearer {token}"}

    client.app.dependency_overrides[get_object_storage] = FakeStorage
    seed(db_session)
    approve(db_session)
    url = "/internal/caregiver/cases/case_photo_01/medications/SYN-MED-001/photo"
    caregiver = session_headers("caregiver")
    insurer = session_headers("insurer")
    jpeg = {"Content-Type": "image/jpeg"}

    assert client.post(url, content=JPEG, headers={**insurer, **jpeg}).status_code == 403
    assert client.post(url, content=b"%PDF-1.4", headers={**caregiver, **jpeg}).status_code == 415
    pdf = {**caregiver, "Content-Type": "application/pdf"}
    assert client.post(url, content=JPEG, headers=pdf).status_code == 415
    sent = client.post(url, content=JPEG, headers={**caregiver, **jpeg})
    assert (sent.status_code, sent.json()) == (201, {"result": "received"})
    again = client.post(url, content=JPEG, headers={**caregiver, **jpeg})
    assert (again.status_code, again.json()) == (409, {"error": "photo_already_received"})


class LiveFakes:
    def __init__(self):
        self.calls: list[tuple] = []
        self.rendered: list[str] = []

    async def render(self, script):
        self.rendered.append(script.spoken_text_ar)
        return SimpleNamespace(audio=b"ogg")

    async def upload_audio(self, audio, filename):
        return "audio-id"

    async def send_audio(self, to, audio_id):
        self.calls.append(("audio", to))
        return "wamid.audio"

    async def send_text(self, to, text):
        self.calls.append(("text", to, text))
        return "wamid.text"

    async def send_template(self, to, name, language, values):
        self.calls.append(("template", to, name, language, values))
        return "wamid.template"

    async def send_photo_reminder(self, to, media_id=None, language="ar"):
        self.calls.append(("dose_question", to, media_id, language))
        return "wamid.question"


def live_adapter(
    fakes, template: str | None = None, opener: str | None = None, reminder: str | None = None
) -> LiveJourneyDeliveryAdapter:
    adapter = object.__new__(LiveJourneyDeliveryAdapter)
    adapter._whatsapp = adapter._renderer = fakes
    adapter._settings = SimpleNamespace(
        whatsapp_photo_request_template=template,
        whatsapp_opener_template=opener,
        whatsapp_reminder_template=reminder,
    )
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
async def test_live_delivery_speaks_the_photo_request_as_a_voice_note():
    fakes = LiveFakes()
    ref = await live_adapter(fakes).deliver(payload("photo_request", text="Please photograph"))
    assert ref == "wamid.audio"
    assert fakes.calls == [("audio", PATIENT)]
    assert fakes.rendered == ["Please photograph"]


@pytest.mark.anyio
async def test_a_configured_template_carries_the_photo_request_outside_the_24_hour_window():
    fakes = LiveFakes()
    request = payload(
        "photo_request", text="Please photograph", template_values=("1", "2", "Zen"), language="en"
    )
    ref = await live_adapter(fakes, template="hawlak_photo_request").deliver(request)
    assert ref == "wamid.template"
    assert fakes.calls == [("template", PATIENT, "hawlak_photo_request", "en", ["1", "2", "Zen"])]


def test_the_template_wording_is_the_approved_request_wording():
    # Meta's template body must be this text, with {{1}}, {{2}} and {{3}} in place of the values.
    for language in ("ar", "en"):
        assert template_body(language) == PHOTO_REPLIES[language]["request"].format(
            n="{{1}}", total="{{2}}", name="{{3}}"
        )


@pytest.mark.anyio
async def test_live_reminder_without_a_checked_photo_still_asks_taken_or_not():
    fakes = LiveFakes()
    reminder = payload("medication_reminder", voice_script="Dose", language="en")
    ref = await live_adapter(fakes).deliver(reminder)
    assert ref == "wamid.audio,wamid.question"
    # The voice note, then the 1 / 2 question with no photo on it.
    assert fakes.calls == [("audio", PATIENT), ("dose_question", PATIENT, None, "en")]


@pytest.mark.anyio
async def test_the_discharge_voice_note_asks_no_dose_question():
    fakes = LiveFakes()
    ref = await live_adapter(fakes).deliver(payload("discharge_voice_note", voice_script="Hello"))
    assert ref == "wamid.audio"
    assert fakes.calls == [("audio", PATIENT)]


@pytest.mark.anyio
async def test_the_opener_goes_as_its_template_with_no_values():
    fakes = LiveFakes()
    ref = await live_adapter(fakes, opener="hawlak_opener").deliver(
        payload("whatsapp_opener", language="ar", window_open=False)
    )
    assert ref == "wamid.template"
    assert fakes.calls == [("template", PATIENT, "hawlak_opener", "ar", [])]


@pytest.mark.anyio
async def test_a_reminder_outside_the_window_goes_as_the_reminder_template():
    fakes = LiveFakes()
    reminder = payload("medication_reminder", voice_script="Dose", language="en", window_open=False)
    ref = await live_adapter(fakes, reminder="hawlak_reminder").deliver(reminder)
    assert ref == "wamid.template"
    assert fakes.calls == [("template", PATIENT, "hawlak_reminder", "en", ["Dose"])]


@pytest.mark.anyio
async def test_a_reminder_inside_the_window_stays_audio_even_with_a_template():
    fakes = LiveFakes()
    reminder = payload("medication_reminder", voice_script="Dose", language="en")
    ref = await live_adapter(fakes, reminder="hawlak_reminder").deliver(reminder)
    assert ref == "wamid.audio,wamid.question"
