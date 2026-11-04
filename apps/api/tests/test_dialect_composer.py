from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.dialects import DIALECT_PROFILES, dialect_options
from app.schemas.voice import ClinicalFacts, DialectComposeRequest
from app.services.dialect_composer import (
    DialectComposerError,
    MockDialectComposer,
    ProviderDialectComposer,
    UnsafeDialectOutputError,
)


def request_from(plan: dict) -> DialectComposeRequest:
    return DialectComposeRequest(
        synthetic=True,
        case_id=plan["case"]["caseId"],
        plan_id=plan["approvedPlan"]["planId"],
        source_hash=plan["approvedPlan"]["source"]["sourceHash"],
        patient_alias=plan["case"]["patientAlias"],
        dialect_code=plan["case"]["dialectCode"],
        clinical_facts=ClinicalFacts.model_validate(plan["approvedPlan"]["clinicalFacts"]),
    )


def test_dashboard_dialect_options_are_the_only_accepted_codes(plan):
    assert [option["code"] for option in dialect_options()] == [
        "ar-SA-hijazi",
        "ar-SA-najdi",
        "ar-SA-janoubi",
    ]
    assert all(profile.natural_phrasing for profile in DIALECT_PROFILES.values())

    invalid = deepcopy(plan)
    invalid["case"]["dialectCode"] = "ar-SA-generic"
    with pytest.raises(ValidationError):
        request_from(invalid)


@pytest.mark.anyio
async def test_mock_composer_is_fixture_only_and_preserves_facts(plan):
    request = request_from(plan)
    result = await MockDialectComposer().compose(request)
    assert result.patient_alias == "أبو محمد"
    assert result.copied_facts == request.clinical_facts

    wrong = request.model_copy(update={"case_id": "other"})
    with pytest.raises(DialectComposerError):
        await MockDialectComposer().compose(wrong)


@pytest.mark.anyio
async def test_provider_output_with_changed_fact_is_rejected(plan):
    request = request_from(plan)
    raw = {
        "patientAlias": request.patient_alias,
        "dialectCode": request.dialect_code,
        "spokenTextAr": "نص تجريبي",
        "copiedFacts": request.clinical_facts.model_dump(by_alias=True),
        "prohibitedContentDetected": False,
        "safetyNotes": [],
    }
    changed = deepcopy(raw)
    changed["copiedFacts"]["emergencyNumber"] = "998"

    class Provider:
        async def generate(self, **_):
            return changed

    with pytest.raises(UnsafeDialectOutputError):
        await ProviderDialectComposer(Provider()).compose(request)


@pytest.mark.anyio
async def test_provider_receives_explicit_dialect_profile(plan):
    request = request_from(plan)
    seen = {}

    class Provider:
        async def generate(self, **kwargs):
            seen.update(kwargs["input_data"])
            return {
                "patientAlias": request.patient_alias,
                "dialectCode": request.dialect_code,
                "spokenTextAr": "هذي تعليماتك، وخلك منتبه.",
                "copiedFacts": request.clinical_facts.model_dump(by_alias=True),
                "prohibitedContentDetected": False,
                "safetyNotes": [],
            }

    await ProviderDialectComposer(Provider()).compose(request)

    assert seen["dialectProfile"]["label_en"] == "Najdi"
    assert "خلك منتبه" in seen["dialectProfile"]["natural_phrasing"]


@pytest.mark.anyio
async def test_provider_error_is_redacted(plan):
    class Provider:
        async def generate(self, **_):
            raise RuntimeError("sensitive provider detail")

    with pytest.raises(DialectComposerError, match="provider request failed") as caught:
        await ProviderDialectComposer(Provider()).compose(request_from(plan))
    assert "sensitive" not in str(caught.value)
