"""Warm transfer to the care team, built on LiveKit's WarmTransferTask.

Code decides that a call transfers (CallConversation); the model never does. CareTeamHandoff
takes over the patient's call, plays the approved transfer script, and runs the task:
- the patient hears a ringback tone while the care team is dialled into a side room;
- the care team hears a fixed line, and an agent answers their questions about the call;
- only the care team pressing 1 joins them to the patient. A voicemail answers a call but
  never presses 1, so it can never count as a transfer.
"""

from __future__ import annotations

import array
import asyncio
import contextlib
import logging
import math
import re
import tempfile
import wave
from collections.abc import Awaitable, Callable
from functools import cache
from pathlib import Path
from typing import Any

from livekit.agents import Agent
from livekit.agents.beta.workflows import WarmTransferResult, WarmTransferTask
from livekit.agents.llm import ToolError

from .conversation import CallAction

logger = logging.getLogger("hawlak-call-agent")

ACCEPT_DIGIT = "1"
RINGBACK_HZ = 425
RINGBACK_ON_S = 1.2
RINGBACK_OFF_S = 4.6
_RATE = 48000

# Fixed product lines, reviewed here like the photo replies; the language follows the call plan.
TRANSFER_LINES = {
    "ar": {
        "responder": "مكالمة متابعة من حولك. المريض ذكر مشكلة عند السؤال {n}: {question} "
        "اضغط 1 لتوصيلك بالمريض الآن.",
        "callback": "ما قدرت أوصل لفريق الرعاية الحين. بيتصلون عليك قريب إن شاء الله.",
    },
    "en": {
        "responder": "Hawlak follow-up call. The patient raised a concern at question {n}: "
        "{question} Press 1 to be connected to the patient now.",
        "callback": "I couldn't reach the care team right now. They will call you back shortly.",
    },
}


@cache
def ringback() -> str:
    """One ringback cycle as a WAV file; LiveKit's hold-audio player loops it."""
    on = round(RINGBACK_ON_S * _RATE)
    samples = array.array(
        "h", (round(8000 * math.sin(2 * math.pi * RINGBACK_HZ * i / _RATE)) for i in range(on))
    )
    samples.extend([0] * round(RINGBACK_OFF_S * _RATE))
    path = Path(tempfile.gettempdir()) / "hawlak-ringback.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(_RATE)
        out.writeframes(samples.tobytes())
    return str(path)


def briefing(language: str, turns: list[dict[str, Any]]) -> str:
    transcript = "\n".join(
        f"{'Patient' if turn['speaker'] == 'patient' else 'Hawlak'}: {turn['text']}"
        for turn in turns
    )
    return (
        "You are Hawlak's assistant on a transfer call with a member of the patient's care "
        "team. A fixed line has already told them why and asked them to press 1 to be "
        f"connected. Reply in {language}, in one or two short sentences, only to answer "
        "their questions about this call, using only the transcript below. Never give "
        "medical advice. You cannot connect the call yourself: if they want to talk to the "
        "patient, tell them to press 1. If you hear a voicemail greeting or a recorded "
        "message, call voicemail_detected. If they say they cannot take the call, call "
        f"decline_transfer.\n\nTranscript of the follow-up call:\n{transcript}"
    )


class CareTeamTransfer(WarmTransferTask):
    """LiveKit's warm transfer, connected by the care team's key press instead of the model."""

    def __init__(
        self,
        *,
        responder_e164: str,
        sip_trunk_id: str,
        responder_line: str,
        briefing: str,
        llm: Any = None,
        ringing_timeout: float = 30.0,
        accept_timeout: float = 45.0,
    ) -> None:
        super().__init__(
            responder_e164,
            sip_trunk_id=sip_trunk_id,
            ringing_timeout=ringing_timeout,
            hold_audio=ringback(),
            instructions=briefing,
            **({"llm": llm} if llm is not None else {}),
        )
        self._responder_line = responder_line
        self._accept_timeout = accept_timeout
        self._accept_timer: asyncio.TimerHandle | None = None
        self._accept_task: asyncio.Task[None] | None = None

    async def connect_to_caller(self) -> None:
        """Deliberately not a tool: the model must never connect the call."""
        await self._accept()

    async def on_enter(self) -> None:
        await super().on_enter()  # returns once the care team answers, or the task failed
        if self.done() or self._human_agent_sess is None:
            return
        self._human_agent_sess.say(self._responder_line, allow_interruptions=False)
        self._accept_timer = asyncio.get_running_loop().call_later(
            self._accept_timeout, self._not_accepted
        )

    async def _originate_human_agent(self, *, room_name: str, identity: str, room: Any) -> None:
        room.on("sip_dtmf_received", self._on_dtmf)
        await super()._originate_human_agent(room_name=room_name, identity=identity, room=room)

    def _on_dtmf(self, dtmf: Any) -> None:
        participant = getattr(dtmf, "participant", None)
        if (
            dtmf.digit == ACCEPT_DIGIT
            and participant is not None
            and participant.identity == self._human_agent_identity
            and not self.done()
        ):
            self._accept_task = asyncio.ensure_future(self._accept())

    async def _accept(self) -> None:
        if self.done() or self._human_agent_sess is None:
            return
        await self._merge_calls()
        self._set_result(WarmTransferResult(human_agent_identity=self._human_agent_identity))
        # When the patient or the care team hangs up, LiveKit's handler closes the room.
        self._caller_room.on("participant_disconnected", self._on_caller_participant_disconnected)

    def _not_accepted(self) -> None:
        self._set_result(ToolError(f"care team did not press {ACCEPT_DIGIT}"))

    def _set_result(self, result: WarmTransferResult | Exception) -> None:
        if self._accept_timer is not None:
            self._accept_timer.cancel()
        super()._set_result(result)


class CareTeamHandoff(Agent):
    """Holds the patient's call while LiveKit's warm transfer reaches the care team."""

    def __init__(
        self,
        owner: Any,
        action: CallAction,
        *,
        sip_trunk_id: str = "",
        llm: Any = None,
        transfer: Callable[[], Awaitable[object]] | None = None,
    ) -> None:
        super().__init__(instructions="A transfer to the care team is in progress. Stay silent.")
        self._owner = owner
        self._action = action
        self._sip_trunk_id = sip_trunk_id
        self._llm_for_briefing = llm
        self._transfer = transfer or self._warm_transfer
        self._language = owner._plan.language.split("-")[0]
        self._lines = TRANSFER_LINES.get(self._language, TRANSFER_LINES["ar"])

    async def _speak(self, text: str) -> None:
        await self.session.say(text, allow_interruptions=False)

    async def _say(self, text: str) -> None:
        self._owner._add_turn("agent", text, guard="ok")
        await self._speak(text)

    async def on_enter(self) -> None:
        await self._say(self._action.spoken_text)
        try:
            await self._transfer()
            transferred = True
        except Exception as exc:
            logger.error(
                "care team transfer failed",
                extra={"error_type": type(exc).__name__, "reason": _without_numbers(exc)},
            )
            transferred = False
            with contextlib.suppress(Exception):  # the patient may already have hung up
                await self._say(self._lines["callback"])
        await self._owner.finish(self._action, transferred=transferred)
        if transferred:
            self._stop_listening()

    def _stop_listening(self) -> None:
        """The patient and the care team stay connected; LiveKit's transfer closes the room
        when either of them hangs up."""
        self.session.shutdown(drain=False)

    async def _warm_transfer(self) -> WarmTransferResult:
        questions = self._owner._plan.questions
        ids = [question.id for question in questions]
        n = ids.index(self._action.question_id) + 1 if self._action.question_id in ids else 1
        return await CareTeamTransfer(
            responder_e164=self._action.transfer_to or "",
            sip_trunk_id=self._sip_trunk_id,
            responder_line=self._lines["responder"].format(n=n, question=questions[n - 1].prompt),
            briefing=briefing(self._owner._plan.language, self._owner._turns),
            llm=self._llm_for_briefing,
        )


def _without_numbers(exc: Exception) -> str:
    """Provider errors can carry phone numbers; keep only the wording."""
    return re.sub(r"\+?\d[\d\s-]{4,}", "…", str(exc))[:200]
