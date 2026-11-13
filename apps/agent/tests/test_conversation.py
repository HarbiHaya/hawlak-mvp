from hawlak_agent.conversation import (
    AnswerKind,
    ApprovedQuestion,
    CallActionKind,
    CallConversation,
    CallPlan,
)


def plan() -> CallPlan:
    return CallPlan(
        id="plan-synthetic-001",
        case_id="case-synthetic-001",
        version=3,
        approved_at="2026-11-12T09:00:00Z",
        phone_e164="+966500000000",
        participant_label="Synthetic patient",
        language="ar-SA",
        opening_script="مرحباً. هذا اتصال متابعة لخطة الخروج المعتمدة.",
        questions=(
            ApprovedQuestion(id="general", prompt="كيف تشعر الآن؟"),
            ApprovedQuestion(
                id="red-flags",
                prompt="هل ظهرت أي علامة تحذيرية ذكرت في تعليمات الخروج؟",
            ),
        ),
        completion_script="شكراً. تم تسجيل المتابعة.",
        transfer_script="سأحول المكالمة الآن إلى فريق المتابعة.",
        responder_phone_e164="+966511111111",
    )


def test_conversation_speaks_only_approved_lines_and_completes() -> None:
    conversation = CallConversation(plan())

    assert conversation.start().spoken_text == plan().opening_script
    assert conversation.next_question().spoken_text == "كيف تشعر الآن؟"
    assert conversation.record_answer(AnswerKind.CLEAR).spoken_text == (
        "هل ظهرت أي علامة تحذيرية ذكرت في تعليمات الخروج؟"
    )

    completed = conversation.record_answer(AnswerKind.CLEAR)

    assert completed.kind is CallActionKind.COMPLETE
    assert completed.spoken_text == plan().completion_script


def test_red_flag_uncertainty_and_request_all_transfer() -> None:
    for answer in (AnswerKind.RED_FLAG, AnswerKind.UNCERTAIN, AnswerKind.TRANSFER_REQUEST):
        conversation = CallConversation(plan())
        conversation.start()
        conversation.next_question()

        action = conversation.record_answer(answer)

        assert action.kind is CallActionKind.TRANSFER
        assert action.spoken_text == plan().transfer_script
        assert action.transfer_to == plan().responder_phone_e164
        assert action.question_id == "general"
        assert action.answer_kind is answer


def test_conversation_rejects_unapproved_or_incomplete_plan() -> None:
    invalid = plan().model_copy(update={"approved_at": None})

    try:
        CallConversation(invalid)
    except ValueError as exc:
        assert str(exc) == "call plan is not approved"
    else:
        raise AssertionError("unapproved plan must be rejected")


def test_finished_conversation_cannot_accept_more_answers() -> None:
    conversation = CallConversation(plan())
    conversation.start()
    conversation.next_question()
    conversation.record_answer(AnswerKind.RED_FLAG)

    try:
        conversation.record_answer(AnswerKind.CLEAR)
    except RuntimeError as exc:
        assert str(exc) == "call conversation is finished"
    else:
        raise AssertionError("finished conversation must be immutable")


def test_current_question_is_the_one_awaiting_an_answer() -> None:
    conversation = CallConversation(plan())
    conversation.start()
    assert conversation.current_question is None

    conversation.next_question()
    assert conversation.current_question == "كيف تشعر الآن؟"

    conversation.record_answer(AnswerKind.CLEAR)
    assert conversation.current_question == "هل ظهرت أي علامة تحذيرية ذكرت في تعليمات الخروج؟"
