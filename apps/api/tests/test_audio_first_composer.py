import pytest

from app.schemas.voice import ClinicalFacts, DialectComposeRequest
from app.services.audio_first_composer import MockAudioFirstComposer


def request_from(plan):
    return DialectComposeRequest(
        synthetic=True,
        case_id=plan["case"]["caseId"],
        plan_id=plan["approvedPlan"]["planId"],
        source_hash=plan["approvedPlan"]["source"]["sourceHash"],
        patient_alias=plan["case"]["patientAlias"],
        dialect_code=plan["case"]["dialectCode"],
        clinical_facts=ClinicalFacts.model_validate(plan["approvedPlan"]["clinicalFacts"]),
    )


@pytest.mark.anyio
async def test_mock_audio_first_composer_separates_session_from_recovery(plan):
    result = await MockAudioFirstComposer().compose(request_from(plan))

    assert "صور" in result.session_summary_ar
    assert "Fictional medicine A" in result.session_summary_ar
    assert "997" not in result.session_summary_ar
    assert "997" in result.recovery_warning_ar
    assert "Fictional medicine A" not in result.recovery_warning_ar
