from test_conversation import plan

from hawlak_agent.conversation import AnswerKind, CallAction, CallActionKind
from hawlak_agent.speech_guard import agent_instructions, check_speech, directive


def facts_plan():
    return plan().model_copy(update={"approved_facts": ("امش ٢٠ دقيقة كل يوم.",)})


def test_a_number_not_in_the_plan_is_rejected() -> None:
    assert check_speech("take 3 tablets now", facts_plan()) is False
    assert check_speech("خذ ٣ حبات", facts_plan()) is False


def test_a_number_from_the_approved_facts_passes_in_either_digit_form() -> None:
    assert check_speech("امش 20 دقيقة.", facts_plan()) is True
    assert check_speech("امش ٢٠ دقيقة.", facts_plan()) is True


def test_a_sentence_over_40_words_is_rejected() -> None:
    assert check_speech(" ".join(["كلمة"] * 40), facts_plan()) is True
    assert check_speech(" ".join(["كلمة"] * 41), facts_plan()) is False


def test_next_question_directive_asks_the_approved_prompt() -> None:
    action = CallAction(
        kind=CallActionKind.SPEAK, spoken_text="كيف تشعر الآن؟", question_id="general"
    )

    text = directive(action)

    assert "Acknowledge briefly" in text
    assert "كيف تشعر الآن؟" in text


def test_clarify_directive_limits_answers_to_approved_facts() -> None:
    action = CallAction(
        kind=CallActionKind.CLARIFY,
        spoken_text="كيف تشعر الآن؟",
        question_id="general",
        answer_kind=AnswerKind.QUESTION,
    )

    text = directive(action)

    assert "only from the approved facts" in text
    assert "care team" in text
    assert text.rstrip().endswith("كيف تشعر الآن؟")


def test_instructions_carry_the_facts_and_forbid_advice() -> None:
    text = agent_instructions(facts_plan())

    assert "امش ٢٠ دقيقة كل يوم." in text
    assert "Never give medical advice" in text


def test_unheard_directive_asks_again_without_answering() -> None:
    action = CallAction(
        kind=CallActionKind.CLARIFY,
        spoken_text="كيف تشعر الآن؟",
        question_id="general",
        answer_kind=AnswerKind.NOT_HEARD,
    )

    text = directive(action)

    assert "did not catch" in text
    assert text.rstrip().endswith("كيف تشعر الآن؟")
