"""Stand-in for the insurer's member and eligibility systems.

ponytail: deterministic mock keyed by member ID; swap for the insurer's eligibility API
(same check_eligibility/enroll shape) when a pilot insurer provides one.
Demo rules: an ID ending in 00 has a lapsed policy, an ID ending in 99 is unknown.
"""

from datetime import date, timedelta
from hashlib import sha256

PLANS = (
    ("Comprehensive Gold", "Network A — Premium hospitals"),
    ("Family Silver", "Network B — Major hospitals"),
    ("Essential Blue", "Network C — General hospitals"),
)
CASE_MANAGERS = (
    ("Nora Al-Qahtani", "+966500000101"),
    ("Faisal Al-Harbi", "+966500000102"),
    ("Reem Al-Dosari", "+966500000103"),
)


class MockInsurerSystems:
    def __init__(self, today: date | None = None) -> None:
        self._today = today or date.today()

    def check_eligibility(self, member_id: str) -> dict:
        if member_id.endswith("99"):
            return {"memberId": member_id, "status": "not_found"}
        seed = int(sha256(member_id.encode()).hexdigest(), 16)
        plan, network = PLANS[seed % len(PLANS)]
        manager, phone = CASE_MANAGERS[(seed // 7) % len(CASE_MANAGERS)]
        lapsed = member_id.endswith("00")
        start = date(self._today.year - (1 if lapsed else 0), 1, 1)
        end = date(start.year, 12, 31) if not lapsed else self._today - timedelta(days=30)
        record = {
            "memberId": member_id,
            "status": "not_eligible" if lapsed else "eligible",
            "policyNumber": f"POL-{seed % 10**8:08d}",
            "plan": plan,
            "network": network,
            "coverageStart": start.isoformat(),
            "coverageEnd": end.isoformat(),
            "program": "post_discharge_care",
            "caseManager": {"name": manager, "phoneE164": phone},
        }
        if lapsed:
            record["reason"] = "policy_lapsed"
        return record

    def enroll(self, case_id: str, eligibility: dict) -> str:
        digest = sha256(f"{case_id}:{eligibility['policyNumber']}".encode()).hexdigest()
        return f"ENR-{self._today.year}-{digest[:6].upper()}"
