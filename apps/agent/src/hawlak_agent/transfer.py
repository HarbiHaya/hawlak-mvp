"""Warm transfer: dial the care team into the call and connect only when a person accepts.

SIP REFER hands the patient to the carrier and reports success as soon as the carrier accepts the
request, whether or not anyone answers. Here the agent dials the responder into the same room,
and only a key press counts: a voicemail answers a call but never presses 1.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

logger = logging.getLogger("hawlak-call-agent")

RESPONDER_IDENTITY = "care-team"

# Fixed product lines, reviewed here like the photo replies; the language follows the call plan.
TRANSFER_LINES = {
    "ar": {
        "responder": "مكالمة متابعة من حولك. المريض ذكر مشكلة عند السؤال {n}. "
        "اضغط 1 لاستلام المكالمة.",
        "callback": "ما قدرت أوصل لفريق الرعاية الحين. بيتصلون عليك قريب إن شاء الله.",
    },
    "en": {
        "responder": "Hawlak follow-up call. The patient raised a concern at question {n}. "
        "Press 1 to take the call.",
        "callback": "I couldn't reach the care team right now. They will call you back shortly.",
    },
}


class SipControl(Protocol):
    async def dial(self, to: str, identity: str) -> None: ...

    async def wait_for_digit(self, identity: str, digit: str, timeout: float) -> bool: ...

    async def remove(self, identity: str) -> None: ...


async def warm_transfer(
    sip: SipControl,
    *,
    responder_e164: str,
    say: Callable[[str], Awaitable[object]],
    language: str,
    question_number: int,
    answer_timeout: float = 30,
    accept_timeout: float = 30,
) -> bool:
    lines = TRANSFER_LINES.get(language, TRANSFER_LINES["ar"])
    try:
        await asyncio.wait_for(sip.dial(responder_e164, RESPONDER_IDENTITY), answer_timeout)
    except Exception as exc:
        logger.error("care team did not answer", extra={"error_type": type(exc).__name__})
        await say(lines["callback"])
        return False

    await say(lines["responder"].format(n=question_number))
    if await sip.wait_for_digit(RESPONDER_IDENTITY, "1", accept_timeout):
        return True

    try:
        await sip.remove(RESPONDER_IDENTITY)
    except Exception as exc:
        logger.error("care team leg removal failed", extra={"error_type": type(exc).__name__})
    await say(lines["callback"])
    return False
