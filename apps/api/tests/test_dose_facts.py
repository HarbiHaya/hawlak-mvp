"""Dose details come from fixed fields, each with its source. Code calculates; nobody guesses."""

from datetime import UTC, datetime

from app.schemas.care_journey import CareJourneyCreate
from app.services.care_journey_service import CareJourneyService
from app.services.discharge_parser import DischargeExtraction
from app.services.dose_facts import dose_facts, reminder_medication_id, reminder_run_times
from app.services.journey_drafter import (
    DraftRejected,
    LiveJourneyDrafter,
    TemplateJourneyDrafter,
    guard_draft,
)

UNKNOWN = {"value": None, "source": "unknown"}


def med(instruction: str, strength: str | None = None, times: tuple[str, ...] = ()) -> dict:
    # Fictional medicine only.
    return {
        "medicationId": "SYN-MED-001",
        "displayName": "Zentorin",
        "doseInstruction": instruction,
        "dispensed": True,
        "reminderEnabled": True,
        "reminderScript": "Time for Zentorin.",
        "unitStrength": strength,
        "reminderTimes": list(times),
    }


def units(instruction: str, strength: str | None) -> dict:
    return dose_facts(med(instruction, strength))["unitsPerDose"]


def test_every_fact_carries_its_source():
    assert dose_facts(med("40 mg twice daily", "40 mg", ("08:00", "20:00"))) == {
        "prescribedDose": {"value": "40 mg", "source": "prescribed"},
        "unitsPerDose": {"value": 1, "source": "calculated"},
        "reminderTimes": {"value": ["08:00", "20:00"], "source": "reminder_preference"},
    }


def test_missing_inputs_stay_unknown():
    facts = dose_facts(med("40 mg twice daily"))
    assert facts["unitsPerDose"] == {**UNKNOWN, "reason": "unit_strength_unknown"}
    # "Twice daily" is a frequency, not a clock time.
    assert facts["reminderTimes"] == {"value": [], "source": "unknown"}
    # A medicine saved before these fields existed has neither key.
    old = {"medicationId": "SYN-MED-001", "displayName": "Zentorin", "doseInstruction": "x"}
    assert dose_facts(old)["prescribedDose"] == UNKNOWN


def test_units_per_dose_is_the_prescribed_dose_divided_by_the_confirmed_strength():
    assert units("2.5 mg once daily", "2.5 mg") == {"value": 1, "source": "calculated"}
    assert units("5 mg once daily", "2.5 mg") == {"value": 2, "source": "calculated"}
    # Arabic-Indic digits and Arabic units read the same.
    assert units("٤٠ ملغ مرتين يومياً", "40 mg") == {"value": 1, "source": "calculated"}


def test_units_per_dose_is_never_guessed():
    # Half a tablet: splitting needs a pharmacist, so code gives no count.
    assert units("20 mg daily", "40 mg") == {**UNKNOWN, "reason": "not_whole_unit"}
    assert units("1 g daily", "500 mg") == {**UNKNOWN, "reason": "unit_mismatch"}
    assert units("10 ml twice daily", "10 ml") == {**UNKNOWN, "reason": "unit_mismatch"}
    # Two different doses in one instruction: which one is "the" dose is not code's call.
    assert units("5 mg morning and 10 mg evening", "5 mg") == {
        **UNKNOWN,
        "reason": "prescribed_dose_unknown",
    }
    assert units("One tablet every morning", "5 mg")["reason"] == "prescribed_dose_unknown"
    # The count is already written, and 500 mg here is the strength, not the dose.
    assert units("Two 500 mg tablets twice daily", "500 mg") == {
        **UNKNOWN,
        "reason": "count_already_prescribed",
    }
    # "2 green tablets" is not 2 g.
    assert dose_facts(med("Take 2 green tablets"))["prescribedDose"] == UNKNOWN


def test_reminders_run_at_the_next_chosen_time_in_saudi_time():
    approved = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)  # 13:00 in Riyadh
    assert reminder_run_times(["08:00", "20:00"], approved) == [
        ("08:00", datetime(2026, 11, 14, 5, 0, tzinfo=UTC)),
        ("20:00", datetime(2026, 11, 13, 17, 0, tzinfo=UTC)),
    ]
    assert reminder_medication_id("medications:SYN-MED-001@08:00") == "SYN-MED-001"
    assert reminder_medication_id("medications:SYN-MED-001") == "SYN-MED-001"


def intake(medication: dict) -> dict:
    return {
        "caseId": "case_dose_01",
        "patientName": "Synthetic Patient One",
        "phoneE164": "+966500000000",
        "languageCode": "en",
        "dialectCode": "ar-SA-najdi",
        "sourceDocument": {"objectKey": "cases/case_dose_01/media/d.pdf", "filename": "d.pdf"},
        "dischargeVoiceNote": {"enabled": False, "script": ""},
        "medications": [medication],
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


def approve(db_session, medication: dict):
    service = CareJourneyService(db_session)
    service.intake(CareJourneyCreate.model_validate(intake(medication)))
    service.check_eligibility("case_dose_01", "SYN-4471203")
    runs = service.approve("case_dose_01", "SYN-REVIEWER", "approve-dose")
    return service, [r for r in runs if r.kind == "medication_reminder"]


def test_approval_schedules_one_reminder_per_chosen_time(db_session):
    service, reminders = approve(db_session, med("40 mg twice daily", "40 mg", ("08:00", "20:00")))

    assert [r.content_ref for r in reminders] == [
        "medications:SYN-MED-001@08:00",
        "medications:SYN-MED-001@20:00",
    ]
    assert all(r.scheduled_at > service._get("case_dose_01")[0].approved_at for r in reminders)
    assert service.detail("case_dose_01")["doseFacts"]["SYN-MED-001"]["unitsPerDose"] == {
        "value": 1,
        "source": "calculated",
    }
    assert service.caregiver("case_dose_01")["medications"][0]["status"] == "scheduled"


def test_without_chosen_times_the_reminder_still_goes_at_approval(db_session):
    service, reminders = approve(db_session, med("40 mg twice daily"))

    assert [r.content_ref for r in reminders] == ["medications:SYN-MED-001"]
    assert reminders[0].scheduled_at == service._get("case_dose_01")[0].approved_at


def test_reminder_times_must_be_clock_times():
    for bad in ("8am", "24:00", "08:60"):
        try:
            CareJourneyCreate.model_validate(intake(med("40 mg", None, (bad,))))
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


EXTRACTION = DischargeExtraction(status="parsed", text="Zentorin 40 mg twice daily")


def test_the_template_states_the_calculated_count_and_nothing_when_unknown():
    drafter = TemplateJourneyDrafter()
    known = drafter.draft(EXTRACTION, [med("40 mg twice daily", "20 mg")], None, "en")
    unknown = drafter.draft(EXTRACTION, [med("40 mg twice daily")], None, "en")

    count = "Number of tablets or capsules per dose: 2."
    assert count in known.reminder_scripts["SYN-MED-001"] and count not in known.voice_script
    assert "per dose" not in unknown.reminder_scripts["SYN-MED-001"] + unknown.voice_script


class FakeModel:
    def __init__(self, reminder: str):
        self.reminder = reminder
        self.payload: dict = {}

    def generate(self, prompt: str, payload: dict) -> dict:
        self.payload = payload
        return {
            "voiceScript": "Your medicines come in separate messages.",
            "reminderScripts": [{"medicationId": "SYN-MED-001", "script": self.reminder}],
            "callOpening": "Hello.",
            "callQuestions": [],
            "callCompletion": "Thank you.",
            "callTransfer": "Please hold.",
        }


def test_the_model_gets_the_fixed_fields_and_only_phrases_them():
    model = FakeModel("Time for Zentorin, 2 tablets, at 08:00.")
    medication = med("40 mg twice daily", "20 mg", ("08:00",))

    draft = LiveJourneyDrafter(model, "test").draft(EXTRACTION, [medication], None, "en")

    assert draft.generator == "openai:test"  # 2 and 08:00 are allowed: they are fixed fields
    assert model.payload["medications"][0]["unitsPerDose"] == 2
    assert model.payload["medications"][0]["reminderTimes"] == ["08:00"]


def test_a_count_or_interval_the_model_worked_out_itself_is_rejected():
    for invented in ("Time for Zentorin, 3 tablets.", "Zentorin every 12 hours."):
        draft = LiveJourneyDrafter(FakeModel(invented), "test").draft(
            EXTRACTION, [med("40 mg twice daily")], None, "en"
        )
        assert draft.generator == "template" and "live_draft_rejected" in draft.notes
    try:
        guard_draft(
            TemplateJourneyDrafter().draft(EXTRACTION, [med("40 mg twice daily")], None, "en"),
            EXTRACTION,
            [med("40 mg twice daily")],
        )
    except DraftRejected as exc:  # the template itself always passes
        raise AssertionError(str(exc)) from exc
