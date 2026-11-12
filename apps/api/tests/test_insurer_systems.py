from datetime import date

from app.services.insurer_systems import MockInsurerSystems


def test_active_member_is_eligible_with_a_stable_policy_record():
    systems = MockInsurerSystems(today=date(2026, 11, 12))

    first = systems.check_eligibility("SYN-4471203")
    again = systems.check_eligibility("SYN-4471203")

    assert first == again
    assert first["status"] == "eligible"
    assert first["memberId"] == "SYN-4471203"
    assert first["policyNumber"].startswith("POL-")
    assert first["coverageStart"] <= "2026-11-12" <= first["coverageEnd"]
    assert first["caseManager"]["phoneE164"].startswith("+9665")
    assert first["program"] == "post_discharge_care"


def test_lapsed_and_unknown_members_are_not_eligible():
    systems = MockInsurerSystems(today=date(2026, 11, 12))

    lapsed = systems.check_eligibility("SYN-1000000")
    unknown = systems.check_eligibility("SYN-1000099")

    assert lapsed["status"] == "not_eligible"
    assert lapsed["reason"] == "policy_lapsed"
    assert lapsed["coverageEnd"] < "2026-11-12"
    assert unknown == {"memberId": "SYN-1000099", "status": "not_found"}


def test_enrollment_reference_is_derived_from_case_and_policy():
    systems = MockInsurerSystems(today=date(2026, 11, 12))

    reference = systems.enroll("case_poc_01", systems.check_eligibility("SYN-4471203"))

    assert reference == systems.enroll("case_poc_01", systems.check_eligibility("SYN-4471203"))
    assert reference.startswith("ENR-2026-")
