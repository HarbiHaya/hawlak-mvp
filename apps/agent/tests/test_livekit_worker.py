import asyncio
import logging
import os
from types import SimpleNamespace

import pytest
from livekit import api

from hawlak_agent.conversation import AnswerKind, CallAction, CallActionKind

os.environ.setdefault("HAWLAK_API_BASE_URL", "http://api:3000")
os.environ.setdefault("HAWLAK_INTERNAL_API_TOKEN", "synthetic-internal-token")
os.environ.setdefault("HAWLAK_CONTROL_TOKEN", "synthetic-control-token")

from hawlak_agent import livekit_worker  # noqa: E402
from hawlak_agent.livekit_worker import HawlakFollowUpAgent  # noqa: E402


class TestAgent(HawlakFollowUpAgent):
    __test__ = False

    def __init__(self, outcome_client, events):
        self._plan = SimpleNamespace(id="run-synthetic-001")
        self.outcome_client = outcome_client
        self._outcome_tasks = set()
        self.events = events

    async def _transfer(self, transfer_to):
        self.events.append(("transfer", transfer_to))
        return True

    async def _end_call(self):
        self.events.append(("end", None))


class FakeOutcomeClient:
    def __init__(self, events, *, fail=False):
        self.events = events
        self.fail = fail

    async def record_completed(self, run_id):
        self.events.append(("report_completed", run_id))
        if self.fail:
            raise RuntimeError("sensitive transcript +966500000000")

    async def record_transferred(self, run_id, *, question_id, answer_kind):
        self.events.append(("report_transferred", run_id, question_id, answer_kind))
        if self.fail:
            raise RuntimeError("sensitive transcript +966500000000")

    async def record_failed(self, run_id, *, question_id, answer_kind):
        self.events.append(("report_failed", run_id, question_id, answer_kind))
        if self.fail:
            raise RuntimeError("sensitive transcript +966500000000")


def test_worker_transfers_before_reporting_structured_outcome() -> None:
    events = []
    agent = TestAgent(FakeOutcomeClient(events), events)
    action = CallAction(
        kind=CallActionKind.TRANSFER,
        spoken_text="Approved transfer",
        transfer_to="+966511111111",
        question_id="red-flags",
        answer_kind=AnswerKind.RED_FLAG,
    )

    asyncio.run(agent._handle_terminal_action(action))

    assert events == [
        ("transfer", "+966511111111"),
        (
            "report_transferred",
            "run-synthetic-001",
            "red-flags",
            AnswerKind.RED_FLAG,
        ),
    ]


def test_reporting_failure_does_not_prevent_completed_call_end(caplog) -> None:
    events = []
    agent = TestAgent(FakeOutcomeClient(events, fail=True), events)
    action = CallAction(kind=CallActionKind.COMPLETE, spoken_text="Approved completion")

    with caplog.at_level(logging.ERROR, logger="hawlak-call-agent"):
        asyncio.run(agent._handle_terminal_action(action))

    assert events == [
        ("end", None),
        ("report_completed", "run-synthetic-001"),
    ]
    assert "call outcome reporting failed" in caplog.text
    assert "sensitive transcript" not in caplog.text
    assert "+966500000000" not in caplog.text


@pytest.mark.parametrize("transfer_raises", [False, True])
def test_failed_transfer_reports_failed_then_safely_ends_room(transfer_raises, caplog) -> None:
    events = []

    class FailedTransferAgent(TestAgent):
        async def _transfer(self, transfer_to):
            self.events.append(("transfer", transfer_to))
            if transfer_raises:
                raise RuntimeError("provider request +966511111111")
            return False

    agent = FailedTransferAgent(FakeOutcomeClient(events), events)
    action = CallAction(
        kind=CallActionKind.TRANSFER,
        spoken_text="Approved transfer",
        transfer_to="+966511111111",
        question_id="red-flags",
        answer_kind=AnswerKind.UNCERTAIN,
    )

    with caplog.at_level(logging.ERROR, logger="hawlak-call-agent"):
        asyncio.run(agent._handle_terminal_action(action))

    assert events == [
        ("transfer", "+966511111111"),
        ("end", None),
        (
            "report_failed",
            "run-synthetic-001",
            "red-flags",
            AnswerKind.UNCERTAIN,
        ),
    ]
    assert "provider request" not in caplog.text
    assert "+966511111111" not in caplog.text


def test_livekit_transfer_requires_explicit_success_status(monkeypatch, caplog) -> None:
    class FakeSip:
        async def transfer_sip_participant(self, request):
            return SimpleNamespace(status=api.STS_TRANSFER_FAILED)

    context = SimpleNamespace(
        api=SimpleNamespace(sip=FakeSip()),
        room=SimpleNamespace(name="synthetic-room"),
    )
    monkeypatch.setattr(livekit_worker, "get_job_context", lambda: context)
    agent = SimpleNamespace(participant_identity="patient-synthetic")

    with caplog.at_level(logging.ERROR, logger="hawlak-call-agent"):
        result = asyncio.run(HawlakFollowUpAgent._transfer(agent, "+966511111111"))

    assert result is False
    assert "+966511111111" not in caplog.text
    assert "synthetic-room" not in caplog.text


def test_livekit_transfer_exception_is_a_safe_failure(monkeypatch, caplog) -> None:
    class FakeSip:
        async def transfer_sip_participant(self, request):
            raise RuntimeError("request detail +966511111111")

    context = SimpleNamespace(
        api=SimpleNamespace(sip=FakeSip()),
        room=SimpleNamespace(name="synthetic-room"),
    )
    monkeypatch.setattr(livekit_worker, "get_job_context", lambda: context)
    agent = SimpleNamespace(participant_identity="patient-synthetic")

    with caplog.at_level(logging.ERROR, logger="hawlak-call-agent"):
        result = asyncio.run(HawlakFollowUpAgent._transfer(agent, "+966511111111"))

    assert result is False
    assert "request detail" not in caplog.text
    assert "+966511111111" not in caplog.text


def test_completed_outcome_survives_room_teardown_cancellation() -> None:
    events = []

    class CancellingAgent(TestAgent):
        async def _end_call(self):
            self.events.append(("end", None))
            asyncio.current_task().cancel()
            await asyncio.sleep(0)

    class SlowOutcomeClient(FakeOutcomeClient):
        async def record_completed(self, run_id):
            await asyncio.sleep(0)
            self.events.append(("report_completed", run_id))

    async def exercise():
        agent = CancellingAgent(SlowOutcomeClient(events), events)
        action = CallAction(kind=CallActionKind.COMPLETE, spoken_text="Approved completion")
        with pytest.raises(asyncio.CancelledError):
            await agent._handle_terminal_action(action)
        await asyncio.sleep(0)

    asyncio.run(exercise())

    assert events == [
        ("end", None),
        ("report_completed", "run-synthetic-001"),
    ]


def test_worker_classifies_the_reply_together_with_its_question() -> None:
    from livekit.agents import StopResponse

    from hawlak_agent.conversation import ApprovedQuestion, CallConversation, CallPlan

    plan = CallPlan(
        id="run-synthetic-001",
        case_id="case-synthetic-001",
        version=1,
        approved_at="2026-11-12T09:00:00Z",
        phone_e164="+966500000000",
        participant_label="Synthetic patient",
        language="ar-SA",
        opening_script="مرحباً.",
        questions=(
            ApprovedQuestion(id="breath", prompt="عندك الحين ضيق نفس شديد؟"),
            ApprovedQuestion(id="meds", prompt="أدويتك موجودة عندك؟"),
        ),
        completion_script="شكراً.",
        transfer_script="سأحول المكالمة.",
        responder_phone_e164="+966511111111",
    )
    seen = []

    class Classifier:
        async def classify(self, transcript, *, question=None):
            seen.append((transcript, question))
            return AnswerKind.CLEAR

    class Session:
        async def say(self, text, allow_interruptions=False):
            return None

    class Agent(TestAgent):
        session = Session()

    agent = Agent(FakeOutcomeClient([]), [])
    agent.conversation = CallConversation(plan)
    agent.classifier = Classifier()
    agent.conversation.start()
    agent.conversation.next_question()

    with pytest.raises(StopResponse):
        asyncio.run(agent.on_user_turn_completed(None, SimpleNamespace(text_content="إيه")))

    assert seen == [("إيه", "عندك الحين ضيق نفس شديد؟")]
