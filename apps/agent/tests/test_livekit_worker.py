import asyncio
import logging
import os
from types import SimpleNamespace

import pytest

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
        self._turns = []
        self._verbatim = set()
        self.events = events

    async def _transfer(self, transfer_to, question_id=None):
        self.events.append(("transfer", transfer_to))
        return True

    async def _end_call(self):
        self.events.append(("end", None))

    async def _leave_call(self):
        self.events.append(("leave", None))


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
        ("leave", None),  # the patient and the care team stay connected; no room teardown
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
        async def _transfer(self, transfer_to, question_id=None):
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


def test_worker_transfer_dials_the_care_team_and_never_refers(monkeypatch) -> None:
    calls = []

    async def fake_warm_transfer(sip, **kwargs):
        calls.append(kwargs)
        return True

    class FakeSipApi:
        async def transfer_sip_participant(self, request):
            raise AssertionError("SIP REFER must not be used")

    context = SimpleNamespace(
        api=SimpleNamespace(sip=FakeSipApi()), room=SimpleNamespace(name="synthetic-room")
    )
    monkeypatch.setattr(livekit_worker, "get_job_context", lambda: context)
    monkeypatch.setattr(livekit_worker, "warm_transfer", fake_warm_transfer)
    agent = SimpleNamespace(
        _plan=SimpleNamespace(
            language="ar-SA",
            questions=(SimpleNamespace(id="q-1"), SimpleNamespace(id="red-flags")),
        ),
        _say=None,
    )

    result = asyncio.run(HawlakFollowUpAgent._transfer(agent, "+966511111111", "red-flags"))

    assert result is True
    assert calls[0]["responder_e164"] == "+966511111111"
    assert calls[0]["language"] == "ar"
    assert calls[0]["question_number"] == 2


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

    from livekit.agents import ChatContext

    turn_ctx = ChatContext()
    asyncio.run(agent.on_user_turn_completed(turn_ctx, SimpleNamespace(text_content="إيه")))

    assert seen == [("إيه", "عندك الحين ضيق نفس شديد؟")]
    # The model phrases the next step; the directive carries the approved question.
    assert "أدويتك موجودة عندك؟" in turn_ctx.items[-1].text_content
    assert agent._turns == [{"seq": 1, "speaker": "patient", "text": "إيه", "answerKind": "clear"}]


def guarded_agent():
    from test_conversation import plan

    from hawlak_agent.conversation import CallConversation

    agent = TestAgent(FakeOutcomeClient([]), [])
    agent._plan = plan()
    agent.conversation = CallConversation(agent._plan)
    agent.conversation.start()
    agent.conversation.next_question()
    agent._turns = []
    agent._verbatim = set()
    return agent


async def collect(agent, chunks):
    async def stream():
        for chunk in chunks:
            yield chunk

    return [piece async for piece in agent._guarded(stream())]


def test_a_guarded_sentence_is_replaced_by_the_approved_prompt() -> None:
    agent = guarded_agent()

    spoken = asyncio.run(collect(agent, ["الحمد لله. خذ 3 ", "حبات الحين. وبعدين"]))

    assert "".join(spoken).strip().endswith("كيف تشعر الآن؟")
    assert "3" not in "".join(spoken)
    assert agent._turns[-1]["guard"] == "replaced"
    assert agent._turns[-1]["speaker"] == "agent"


def test_approved_lines_pass_the_guard_verbatim() -> None:
    agent = guarded_agent()
    line = "اضغط 1 لاستلام المكالمة."
    agent._verbatim.add(line)

    spoken = asyncio.run(collect(agent, [line]))

    assert "".join(spoken).strip() == line
    assert agent._turns[-1]["guard"] == "ok"


def test_turns_are_sent_when_the_call_ends() -> None:
    events = []

    class TurnsClient(FakeOutcomeClient):
        async def record_turns(self, run_id, turns):
            self.events.append(("turns", run_id, [t["seq"] for t in turns]))

    agent = TestAgent(TurnsClient(events), events)
    agent._turns = [{"seq": 1, "speaker": "agent", "text": "مرحباً"}]

    asyncio.run(
        agent._handle_terminal_action(
            CallAction(kind=CallActionKind.COMPLETE, spoken_text="Approved completion")
        )
    )

    assert ("turns", "run-synthetic-001", [1]) in events


def test_the_agent_uses_the_chat_llm_not_the_responses_api(monkeypatch) -> None:
    from dataclasses import replace

    monkeypatch.setattr(
        livekit_worker, "settings", replace(livekit_worker.settings, openai_api_key="synthetic")
    )
    from livekit.plugins import openai
    from test_conversation import plan

    agent = HawlakFollowUpAgent(
        plan=plan(), classifier=None, participant_identity="patient-x", outcome_client=None
    )

    assert type(agent.llm) is openai.LLM
