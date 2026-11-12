import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from hawlak_agent.plan_client import ApprovedPlanClient, PlanFetchError

APPROVED_PLAN = {
    "id": "plan-synthetic-001",
    "caseId": "case-synthetic-001",
    "version": 1,
    "approvedAt": "2026-11-12T09:00:00Z",
    "phoneE164": "+966500000000",
    "participantLabel": "Synthetic patient",
    "language": "ar-SA",
    "openingScript": "Approved opening",
    "questions": [{"id": "status", "prompt": "Approved question"}],
    "completionScript": "Approved completion",
    "transferScript": "Approved transfer",
    "responderPhoneE164": "+966511111111",
}


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return BytesIO(json.dumps(self.payload).encode())

    def __exit__(self, *_args):
        return False


def test_client_fetches_plan_with_bearer_token_without_logging_phone() -> None:
    captured = {}

    def open_request(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return FakeResponse(APPROVED_PLAN)

    client = ApprovedPlanClient(
        base_url="https://api.example.test",
        token="internal-secret",
        opener=open_request,
    )

    fetched = client.fetch("plan-synthetic-001")

    assert fetched.id == "plan-synthetic-001"
    assert captured == {
        "url": "https://api.example.test/internal/call-plans/plan-synthetic-001",
        "authorization": "Bearer internal-secret",
        "timeout": 10.0,
    }


def test_client_rejects_path_injection() -> None:
    client = ApprovedPlanClient("https://api.example.test", "token", opener=lambda *_: None)

    with pytest.raises(ValueError, match="invalid call plan id"):
        client.fetch("../cases/other")


def test_client_turns_http_failure_into_safe_error() -> None:
    def fail(request, timeout):
        raise HTTPError(request.full_url, 409, "not approved", {}, None)

    client = ApprovedPlanClient("https://api.example.test", "token", opener=fail)

    with pytest.raises(PlanFetchError, match="call plan is unavailable"):
        client.fetch("plan-synthetic-001")
