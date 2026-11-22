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
    draft.reminder_scripts["PDF-MED-001"] = draft.reminder_scripts["PDF-MED-001"].replace(
        "5 mg", "50 mg"
    )

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
    assert "5 mg" in draft.reminder_scripts["PDF-MED-001"]


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


def instructions_extraction():
    from app.services.discharge_parser import parse_discharge_text

    return parse_discharge_text(
        "\n".join(
            [
                "3. Discharge Medications",
                "• Fictional medicine A 40 mg orally twice daily: For fluid.",
                "4. Lifestyle Modifications",
                "• Low-sodium diet: Limit sodium to less than 2 g/day.",
                "5. Red Flags",
                "• Chest pain.",
                "Emergency number: 997",
            ]
        )
    )


FLUID_MEDS = [
    {"medicationId": "PDF-MED-001", "displayName": "Fictional medicine A 40 mg orally twice daily",
     "doseInstruction": "For fluid."},
]  # fmt: skip


def arabic_draft(voice_script: str):
    from app.services.journey_drafter import JourneyDraft

    return JourneyDraft(
        voice_script=voice_script,
        reminder_scripts={
            "PDF-MED-001": "تذكير من حولك: حان موعد Fictional medicine A 40 mg orally twice daily"
        },
        call_opening="السلام عليكم.",
        call_questions=[],
        call_completion="شكراً.",
        call_transfer="سأحوّلك الآن.",
        generator="openai:test",
    )


def test_template_voice_note_has_no_medicines_but_keeps_stopped_ones(extraction):
    from app.services.journey_drafter import TEXT

    for language in ("en", "ar"):
        draft = TemplateJourneyDrafter().draft(extraction, MEDICATIONS, None, language)

        assert "Fictional medicine A" not in draft.voice_script
        assert "Fictional medicine D" in draft.voice_script
        assert TEXT[language]["medicines_elsewhere"] in draft.voice_script
        assert "Fictional medicine A" in draft.reminder_scripts["PDF-MED-001"]
        guard_draft(draft, extraction, MEDICATIONS)


def test_guard_accepts_an_arabic_voice_note_for_an_english_document():
    draft = arabic_draft(
        "السلام عليكم. قلل الملح لأقل من 2 غرام في اليوم. إذا حسيت بألم في الصدر اتصل على 997."
    )

    guard_draft(draft, instructions_extraction(), FLUID_MEDS)


def test_guard_rejects_a_voice_note_that_names_a_dispensed_medicine():
    draft = arabic_draft("قلل الملح لأقل من 2 غرام. خذ fictional medicine a صباحاً.")

    with pytest.raises(DraftRejected, match="medicine in the voice note"):
        guard_draft(draft, instructions_extraction(), FLUID_MEDS)


def test_guard_allows_an_instruction_that_shares_a_medicines_first_word():
    meds = [{"medicationId": "PDF-MED-001", "displayName": "Renal multivitamin, one tablet",
             "doseInstruction": "If prescribed."}]  # fmt: skip
    draft = arabic_draft("قلل الملح لأقل من 2 غرام. راجع أخصائي التغذية renal dietitian.")
    draft.reminder_scripts = {"PDF-MED-001": "تذكير: Renal multivitamin, one tablet"}

    guard_draft(draft, instructions_extraction(), meds)


def test_guard_rejects_a_voice_note_that_drops_an_instruction_number():
    draft = arabic_draft("السلام عليكم. قلل الملح. إذا حسيت بألم في الصدر اتصل على 997.")

    with pytest.raises(DraftRejected, match="instruction number missing from the voice note"):
        guard_draft(draft, instructions_extraction(), FLUID_MEDS)


def test_guard_still_rejects_a_reminder_without_its_medicine_name():
    draft = arabic_draft("قلل الملح لأقل من 2 غرام. اتصل على 997.")
    draft.reminder_scripts = {"PDF-MED-001": "تذكير من حولك: حان موعد الدواء"}

    with pytest.raises(DraftRejected, match="medicine missing from its reminder"):
        guard_draft(draft, instructions_extraction(), FLUID_MEDS)
