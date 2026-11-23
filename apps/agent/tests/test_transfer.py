import asyncio
import logging

from hawlak_agent.transfer import TRANSFER_LINES, warm_transfer

RESPONDER = "+966511111111"


class FakeSip:
    def __init__(self, *, answers=True, presses=True):
        self.answers = answers
        self.presses = presses
        self.events: list[tuple] = []

    async def dial(self, to, identity):
        self.events.append(("dial", to, identity))
        if not self.answers:
            raise RuntimeError(f"no answer from {to}")

    async def wait_for_digit(self, identity, digit, timeout):
        self.events.append(("wait", identity, digit, timeout))
        return self.presses

    async def remove(self, identity):
        self.events.append(("remove", identity))


def run(sip, language="ar"):
    said: list[str] = []

    async def say(text):
        said.append(text)

    accepted = asyncio.run(
        warm_transfer(sip, responder_e164=RESPONDER, say=say, language=language, question_number=2)
    )
    return accepted, said


def test_transfer_counts_only_after_the_responder_presses_1():
    sip = FakeSip()

    accepted, said = run(sip)

    assert accepted is True
    assert said == [TRANSFER_LINES["ar"]["responder"].format(n=2)]
    assert ("wait", "care-team", "1", 30) in sip.events
    assert ("remove", "care-team") not in sip.events


def test_voicemail_without_a_key_press_is_not_a_transfer():
    sip = FakeSip(presses=False)

    accepted, said = run(sip, language="en")

    assert accepted is False
    assert said == [
        TRANSFER_LINES["en"]["responder"].format(n=2),
        TRANSFER_LINES["en"]["callback"],
    ]
    assert sip.events[-1] == ("remove", "care-team")


def test_no_answer_is_not_a_transfer_and_logs_no_number(caplog):
    sip = FakeSip(answers=False)

    with caplog.at_level(logging.ERROR, logger="hawlak-call-agent"):
        accepted, said = run(sip)

    assert accepted is False
    assert said == [TRANSFER_LINES["ar"]["callback"]]
    assert RESPONDER not in caplog.text


def test_every_language_has_both_fixed_lines():
    for lines in TRANSFER_LINES.values():
        assert set(lines) == {"responder", "callback"}
        assert "{n}" in lines["responder"]
