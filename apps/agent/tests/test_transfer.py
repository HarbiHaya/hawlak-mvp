import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("HAWLAK_API_BASE_URL", "http://api:3000")
os.environ.setdefault("HAWLAK_INTERNAL_API_TOKEN", "synthetic-internal-token")
os.environ.setdefault("HAWLAK_CONTROL_TOKEN", "synthetic-control-token")

from livekit.agents.llm import ToolError  # noqa: E402

from hawlak_agent.conversation import AnswerKind, CallAction, CallActionKind  # noqa: E402
from hawlak_agent.transfer import (  # noqa: E402
    RINGBACK_OFF_S,
    RINGBACK_ON_S,
    TRANSFER_LINES,
    CareTeamHandoff,
    CareTeamTransfer,
    ringback,
)

RESPONDER = "+966511111111"
ACTION = CallAction(
    kind=CallActionKind.TRANSFER,
    spoken_text="سأحولك الآن إلى فريق الرعاية.",
    question_id="warning-2",
    answer_kind=AnswerKind.RED_FLAG,
    transfer_to=RESPONDER,
)


def transfer_task(**kwargs):
    return CareTeamTransfer(
        responder_e164=RESPONDER,
        sip_trunk_id="ST_synthetic",
        responder_line="Press 1.",
        briefing="Brief the care team.",
        **kwargs,
    )


def test_ringback_is_one_tone_then_silence_cycle_for_livekit_to_loop() -> None:
    import array
    import wave

    with wave.open(ringback()) as audio:
        rate = audio.getframerate()
        samples = array.array("h", audio.readframes(audio.getnframes()))

    on = round(RINGBACK_ON_S * rate)
    assert audio.getnchannels() == 1 and rate == 48000
    assert len(samples) == on + round(RINGBACK_OFF_S * rate)
    assert max(samples[:on]) > 1000
    assert not any(samples[on:])


def test_only_pressing_1_connects_the_care_team() -> None:
    async def tool_names():
        return {tool.info.name for tool in transfer_task().tools}

    names = asyncio.run(tool_names())

    assert "connect_to_caller" not in names  # the model can never connect the call
    assert {"decline_transfer", "voicemail_detected"} <= names


def test_a_1_from_the_care_team_connects_and_other_keys_do_not() -> None:
    async def presses():
        task = transfer_task()
        accepted = []

        async def accept():
            accepted.append(True)

        task._accept = accept
        for digit, identity in (
            ("2", task._human_agent_identity),
            ("1", "patient-x"),
            ("1", task._human_agent_identity),
        ):
            before = len(accepted)
            task._on_dtmf(
                SimpleNamespace(digit=digit, participant=SimpleNamespace(identity=identity))
            )
            await asyncio.sleep(0)
            yield len(accepted) - before

    async def collect():
        return [step async for step in presses()]

    assert asyncio.run(collect()) == [0, 0, 1]


def test_no_key_press_after_answering_fails_the_transfer() -> None:
    async def time_out():
        task = transfer_task()
        results = []
        task._set_result = results.append
        task._not_accepted()
        return results

    assert isinstance(asyncio.run(time_out())[0], ToolError)


class FakeOwner:
    def __init__(self):
        self.events = []
        self._plan = SimpleNamespace(
            language="ar-SA", questions=(SimpleNamespace(id="warning-2", prompt="سؤال؟"),)
        )

    def _add_turn(self, speaker, text, **extra):
        self.events.append(("turn", speaker, text))

    async def finish(self, action, *, transferred=False):
        self.events.append(("finish", action.answer_kind, transferred))


def run_handoff(result):
    owner = FakeOwner()

    async def transfer():
        if isinstance(result, Exception):
            raise result
        return result

    handoff = CareTeamHandoff(owner, ACTION, transfer=transfer)
    said = []

    async def say(text, allow_interruptions=False):
        said.append(text)

    handoff._speak = say
    handoff._stop_listening = lambda: said.append("stopped listening")
    asyncio.run(handoff.on_enter())
    return owner.events, said


def test_an_accepted_transfer_is_reported_as_transferred() -> None:
    events, said = run_handoff(SimpleNamespace(human_agent_identity="human-agent-sip"))

    assert said == [ACTION.spoken_text, "stopped listening"]
    assert events[-1] == ("finish", AnswerKind.RED_FLAG, True)


def test_a_failed_transfer_plays_the_callback_line_and_reports_failed() -> None:
    events, said = run_handoff(ToolError("care team did not answer"))

    assert said == [ACTION.spoken_text, TRANSFER_LINES["ar"]["callback"]]
    assert ("turn", "agent", TRANSFER_LINES["ar"]["callback"]) in events
    assert events[-1] == ("finish", AnswerKind.RED_FLAG, False)
