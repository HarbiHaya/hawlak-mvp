"""What the call model may say: approved facts only, checked sentence by sentence.

Code owns progress (CallConversation picks every step); the model only phrases it.
"""

from __future__ import annotations

import re

from .conversation import CallAction, CallActionKind, CallPlan

MAX_WORDS = 40
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "0123456789" * 2)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text.translate(_DIGITS)))


def plan_text(plan: CallPlan) -> str:
    return "\n".join(
        (
            plan.opening_script,
            *(question.prompt for question in plan.questions),
            plan.completion_script,
            plan.transfer_script,
            *plan.approved_facts,
        )
    )


def check_speech(sentence: str, plan: CallPlan) -> bool:
    # ponytail: digits only; a spelled-out number ("three", "ثلاث") passes. Add a word list
    # per language if rehearsals show the model spelling doses out.
    if len(sentence.split()) > MAX_WORDS:
        return False
    return _numbers(sentence) <= _numbers(plan_text(plan))


def agent_instructions(plan: CallPlan) -> str:
    facts = "\n".join(f"- {fact}" for fact in plan.approved_facts) or "- (none)"
    return (
        "You are Hawlak's follow-up caller, phoning a patient after hospital discharge on "
        "behalf of their care team. Speak the patient's dialect "
        f"({plan.language}), warmly and briefly: one or two short sentences per turn. "
        "Never give medical advice, never change or explain doses, and never state a fact "
        "that is not in the approved facts below. If the patient asks something the facts "
        "do not answer, say the care team will help with it. Each turn you get a system "
        "note with the exact approved question to ask; always end your turn with it.\n"
        f"Approved facts:\n{facts}"
    )


def directive(action: CallAction) -> str:
    # The patient's words stay in their own user message, never in this system note.
    if action.kind is CallActionKind.CLARIFY:
        return (
            "Answer only from the approved facts, or say the care team will help; "
            f"never give advice. Then ask again, in these words: {action.spoken_text}"
        )
    return f"Acknowledge briefly, then ask, in these words: {action.spoken_text}"
