import pytest

from app.services.discharge_parser import parse_discharge_pdf
from app.services.journey_drafter import (
    DraftRejected,
    LiveJourneyDrafter,
    TemplateJourneyDrafter,
    guard_draft,
)

MEDICATIONS = [
    {"medicationId": "PDF-MED-001", "displayName": "Fictional medicine A",
     "doseInstruction": "5 mg, 1 tablet, once daily (morning)"},
]  # fmt: skip


@pytest.fixture
def extraction(fixtures_dir):
    return parse_discharge_pdf((fixtures_dir / "approved-plan.abu-mohammed.pdf").read_bytes())


def test_template_draft_covers_every_fact_in_the_patient_language(extraction):
    draft = TemplateJourneyDrafter().draft(extraction, MEDICATIONS, "Abu Mohammed", "en")

    script = draft.voice_script
    assert script.startswith("Hello Abu Mohammed.")
    assert "Fictional medicine A: 5 mg, 1 tablet, once daily (morning)." in script
    assert "Fictional medicine D" in script  # stopped medicine
    assert "Prefer low-salt meals." in script
    assert "call 997 at once" in script
    assert draft.reminder_scripts["PDF-MED-001"].startswith("Hawlak reminder:")
    assert [q["prompt"] for q in draft.call_questions] == [
        "Since leaving the hospital, have you had new chest pain or pressure?",
        "Since leaving the hospital, have you had shortness of breath?",
    ]
    assert draft.generator == "template"
    guard_draft(draft, extraction, MEDICATIONS)


def test_arabic_template_frames_the_document_facts_in_arabic(extraction):
    draft = TemplateJourneyDrafter().draft(extraction, MEDICATIONS, "أبو محمد", "ar")

    assert draft.voice_script.startswith("السلام عليكم أبو محمد.")
    assert "اتصل على 997 فوراً" in draft.voice_script
    assert draft.call_questions[0]["prompt"].startswith("منذ خروجك من المستشفى")
    guard_draft(draft, extraction, MEDICATIONS)


def test_guard_rejects_a_number_that_is_not_in_the_document(extraction):
    draft = TemplateJourneyDrafter().draft(extraction, MEDICATIONS, "Abu Mohammed", "en")
    draft.voice_script = draft.voice_script.replace("5 mg", "50 mg")

    with pytest.raises(DraftRejected, match="number"):
        guard_draft(draft, extraction, MEDICATIONS)


def test_live_drafter_falls_back_to_the_template_when_the_model_invents_a_dose(extraction):
    class Model:
        def generate(self, prompt, payload):
            return {
                "voiceScript": "Take Fictional medicine A 10 mg twice.",
                "reminderScripts": [],
                "callOpening": "Hi",
                "callQuestions": [],
                "callCompletion": "Bye",
                "callTransfer": "Transferring",
            }

    draft = LiveJourneyDrafter(Model(), "test-model").draft(
        extraction, MEDICATIONS, "Abu Mohammed", "en"
    )

    assert draft.generator == "template"
    assert "5 mg" in draft.voice_script


def test_template_greets_without_a_name_when_no_form_of_address_is_approved(extraction):
    english = TemplateJourneyDrafter().draft(extraction, MEDICATIONS, None, "en")
    arabic = TemplateJourneyDrafter().draft(extraction, MEDICATIONS, None, "ar")

    assert english.voice_script.startswith("Hello. This message from Hawlak")
    assert english.call_opening.startswith("Hello. This is Hawlak")
    assert arabic.voice_script.startswith("السلام عليكم. هذه رسالة من حولك")


def test_live_drafter_never_sends_identifying_notes_to_the_model(extraction):
    seen = {}

    class Model:
        def generate(self, prompt, payload):
            seen.update(payload)
            raise RuntimeError("stop after capturing the payload")

    extraction.notes = [
        "Patient name: Synthetic Patient",
        "MRN: 55120",
        "رقم الهوية: 1098765432",
        "Emergency number: 997",
    ]
    LiveJourneyDrafter(Model(), "test-model").draft(extraction, MEDICATIONS, None, "en")

    assert seen["notes"] == ["Emergency number: 997"]
    assert seen["patientLabel"] is None
