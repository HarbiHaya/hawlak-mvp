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


def test_red_flag_and_request_transfer_at_once() -> None:
    for answer in (AnswerKind.RED_FLAG, AnswerKind.TRANSFER_REQUEST):
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


def started() -> CallConversation:
    conversation = CallConversation(plan())
    conversation.start()
    conversation.next_question()
    return conversation


def test_a_first_question_or_unsure_reply_lets_the_agent_clarify() -> None:
    for kind in (AnswerKind.QUESTION, AnswerKind.UNCERTAIN):
        action = started().record_answer(kind)

        assert action.kind is CallActionKind.CLARIFY
        assert action.question_id == "general"
        assert action.spoken_text == "كيف تشعر الآن؟"  # the approved prompt to come back to


def test_a_second_unclear_reply_on_the_same_question_transfers() -> None:
    conversation = started()
    conversation.record_answer(AnswerKind.QUESTION)

    action = conversation.record_answer(AnswerKind.UNCERTAIN)

    assert action.kind is CallActionKind.TRANSFER
    assert action.answer_kind is AnswerKind.UNCERTAIN


def test_clarifying_one_question_does_not_use_up_the_next_ones() -> None:
    conversation = started()
    conversation.record_answer(AnswerKind.QUESTION)
    conversation.record_answer(AnswerKind.CLEAR)

    assert conversation.record_answer(AnswerKind.QUESTION).kind is CallActionKind.CLARIFY


def test_a_warning_sign_transfers_at_once_even_while_clarifying() -> None:
    for kind in (AnswerKind.RED_FLAG, AnswerKind.TRANSFER_REQUEST):
        conversation = started()
        conversation.record_answer(AnswerKind.QUESTION)

        assert conversation.record_answer(kind).kind is CallActionKind.TRANSFER


def test_cannot_complete_before_every_question_is_answered() -> None:
    conversation = started()

    first = conversation.record_answer(AnswerKind.CLEAR)
    last = conversation.record_answer(AnswerKind.CLEAR)

    assert first.kind is CallActionKind.SPEAK and first.question_id == "red-flags"
    assert last.kind is CallActionKind.COMPLETE


def test_noise_repeats_the_question_without_counting_toward_a_transfer() -> None:
    conversation = CallConversation(plan())
    conversation.start()
    conversation.next_question()

    for _ in range(2):
        action = conversation.record_answer(AnswerKind.NOT_HEARD)
        assert action.kind is CallActionKind.CLARIFY
        assert action.answer_kind is AnswerKind.NOT_HEARD
    assert conversation.record_answer(AnswerKind.QUESTION).kind is CallActionKind.CLARIFY
    assert conversation.record_answer(AnswerKind.CLEAR).kind is CallActionKind.SPEAK


def test_a_third_unheard_reply_transfers() -> None:
    conversation = CallConversation(plan())
    conversation.start()
    conversation.next_question()

    for _ in range(2):
        conversation.record_answer(AnswerKind.NOT_HEARD)
    action = conversation.record_answer(AnswerKind.NOT_HEARD)

    assert action.kind is CallActionKind.TRANSFER
    assert action.answer_kind is AnswerKind.NOT_HEARD
