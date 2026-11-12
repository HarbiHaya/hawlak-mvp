import asyncio
import json
import threading
from io import BytesIO
from urllib.error import HTTPError

import pytest

from hawlak_agent.conversation import AnswerKind
from hawlak_agent.outcome_client import CallOutcomeClient, CallOutcomeReportError


class FakeResponse:
    def __enter__(self):
        return BytesIO(b'{"status":"completed"}')

    def __exit__(self, *_args):
        return False


def test_client_posts_completed_outcome_with_auth_and_idempotency() -> None:
    captured = {}
    caller_thread = threading.get_ident()

    def open_request(request, timeout):
        captured.update(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "authorization": request.headers["Authorization"],
                "content_type": request.headers["Content-type"],
                "idempotency_key": request.headers["Idempotency-key"],
                "body": json.loads(request.data),
                "timeout": timeout,
                "thread": threading.get_ident(),
            }
        )
        return FakeResponse()

    client = CallOutcomeClient(
        "https://api.example.test",
        "internal-secret",
        opener=open_request,
    )

    asyncio.run(client.record_completed("run-synthetic-001"))

    assert captured == {
        "url": ("https://api.example.test/internal/delivery-runs/run-synthetic-001/call-outcome"),
        "method": "POST",
        "authorization": "Bearer internal-secret",
        "content_type": "application/json",
        "idempotency_key": "call-outcome:run-synthetic-001:completed",
        "body": {"status": "completed"},
        "timeout": 10.0,
        "thread": captured["thread"],
    }
    assert captured["thread"] != caller_thread


def test_client_posts_only_structured_transfer_outcome() -> None:
    captured = {}

    def open_request(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["idempotency_key"] = request.headers["Idempotency-key"]
        return FakeResponse()

    client = CallOutcomeClient(
        "https://api.example.test",
        "internal-secret",
        opener=open_request,
    )

    asyncio.run(
        client.record_transferred(
            "run-synthetic-001",
            question_id="red-flags",
            answer_kind=AnswerKind.RED_FLAG,
        )
    )

    assert captured == {
        "body": {
            "status": "transferred",
            "escalation": {
                "questionId": "red-flags",
                "answerKind": "red_flag",
            },
        },
        "idempotency_key": "call-outcome:run-synthetic-001:transferred",
    }
    assert "phone" not in str(captured).lower()
    assert "transcript" not in str(captured).lower()


def test_client_posts_failed_transfer_with_the_same_safe_escalation_shape() -> None:
    captured = {}

    def open_request(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["idempotency_key"] = request.headers["Idempotency-key"]
        return FakeResponse()

    client = CallOutcomeClient(
        "https://api.example.test",
        "internal-secret",
        opener=open_request,
    )

    asyncio.run(
        client.record_failed(
            "run-synthetic-001",
            question_id="red-flags",
            answer_kind=AnswerKind.UNCERTAIN,
        )
    )

    assert captured == {
        "body": {
            "status": "failed",
            "escalation": {
                "questionId": "red-flags",
                "answerKind": "uncertain",
            },
        },
        "idempotency_key": "call-outcome:run-synthetic-001:failed",
    }


def test_client_retries_5xx_with_the_same_idempotency_key() -> None:
    attempts = []

    def fail_then_succeed(request, timeout):
        attempts.append(request.headers["Idempotency-key"])
        if len(attempts) < 3:
            raise HTTPError(request.full_url, 503, "sensitive upstream detail", {}, None)
        return FakeResponse()

    client = CallOutcomeClient(
        "https://api.example.test",
        "internal-secret",
        opener=fail_then_succeed,
        max_attempts=3,
        retry_delay_seconds=0,
    )

    asyncio.run(client.record_completed("run-synthetic-001"))

    assert attempts == [
        "call-outcome:run-synthetic-001:completed",
        "call-outcome:run-synthetic-001:completed",
        "call-outcome:run-synthetic-001:completed",
    ]


def test_client_maps_transport_failure_to_safe_error() -> None:
    attempts = 0

    def fail(request, timeout):
        nonlocal attempts
        attempts += 1
        raise HTTPError(request.full_url, 409, "sensitive provider detail", {}, None)

    client = CallOutcomeClient("https://api.example.test", "internal-secret", opener=fail)

    with pytest.raises(CallOutcomeReportError, match="call outcome could not be recorded") as exc:
        asyncio.run(client.record_completed("run-synthetic-001"))

    assert "sensitive provider detail" not in str(exc.value)
    assert attempts == 1


def test_client_rejects_clear_answer_as_transfer_outcome() -> None:
    client = CallOutcomeClient(
        "https://api.example.test",
        "internal-secret",
        opener=lambda *_args, **_kwargs: FakeResponse(),
    )

    with pytest.raises(ValueError, match="escalation answer"):
        asyncio.run(
            client.record_transferred(
                "run-synthetic-001",
                question_id="status",
                answer_kind=AnswerKind.CLEAR,
            )
        )
