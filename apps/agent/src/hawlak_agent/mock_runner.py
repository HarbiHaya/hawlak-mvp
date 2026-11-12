from __future__ import annotations

from typing import Any

from .conversation import AnswerKind, CallActionKind, CallConversation, CallPlan


def run_mock_call(*, plan_payload: dict[str, Any], answers: list[str]) -> dict[str, Any]:
    """Run the production state machine without LiveKit or provider credentials."""

    conversation = CallConversation(CallPlan.model_validate(plan_payload))
    spoken = [conversation.start().spoken_text, conversation.next_question().spoken_text]
    transfer_last4: str | None = None
    escalation: dict[str, str] | None = None
    status = "incomplete"

    for raw_answer in answers:
        action = conversation.record_answer(AnswerKind(raw_answer))
        spoken.append(action.spoken_text)
        if action.kind is CallActionKind.TRANSFER:
            status = "transferred"
            transfer_last4 = action.transfer_to[-4:] if action.transfer_to else None
            escalation = {
                "answerKind": action.answer_kind.value,
                "questionId": action.question_id,
            }
            break
        if action.kind is CallActionKind.COMPLETE:
            status = "completed"
            break

    return {
        "status": status,
        "spoken": spoken,
        "transferToLast4": transfer_last4,
        "escalation": escalation,
    }
