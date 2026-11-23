import asyncio
import json
from io import BytesIO

from hawlak_agent.classifier import ClassificationError, OpenAIAnswerClassifier
from hawlak_agent.conversation import AnswerKind


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return BytesIO(json.dumps(self.payload).encode())

    def __exit__(self, *_args):
        return False


def test_classifier_uses_strict_enum_and_returns_allowed_answer() -> None:
    captured = {}

    def open_request(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        captured["authorization"] = request.headers["Authorization"]
        return FakeResponse(
            {"output": [{"content": [{"type": "output_text", "text": '{"answer":"red_flag"}'}]}]}
        )

    classifier = OpenAIAnswerClassifier(
        base_url="https://model.example/v1",
        api_key="secret",
        model="classifier-model",
        opener=open_request,
    )

    result = asyncio.run(classifier.classify("عندي ألم شديد"))

    assert result is AnswerKind.RED_FLAG
    assert captured["url"] == "https://model.example/v1/responses"
    assert captured["authorization"] == "Bearer secret"
    assert captured["body"]["text"]["format"]["schema"]["properties"]["answer"]["enum"] == [
        "clear",
        "red_flag",
        "uncertain",
        "transfer_request",
        "question",
        "not_heard",
    ]


def test_classifier_fails_safe_to_uncertain_on_invalid_provider_output() -> None:
    classifier = OpenAIAnswerClassifier(
        base_url="https://model.example/v1",
        api_key="secret",
        model="classifier-model",
        opener=lambda *_args, **_kwargs: FakeResponse({"output": []}),
    )

    try:
        asyncio.run(classifier.classify("ambiguous"))
    except ClassificationError as exc:
        assert "could not be classified" in str(exc)
    else:
        raise AssertionError("invalid provider output must fail closed")


def test_classifier_sends_the_approved_question_with_the_reply() -> None:
    captured = {}

    def open_request(request, timeout):
        captured["body"] = json.loads(request.data)
        return FakeResponse(
            {"output": [{"content": [{"type": "output_text", "text": '{"answer":"red_flag"}'}]}]}
        )

    classifier = OpenAIAnswerClassifier(
        base_url="https://model.example/v1",
        api_key="secret",
        model="classifier-model",
        opener=open_request,
    )
    question = "عندك الحين ضيق نفس شديد؟"

    # A bare "yes" means nothing without the question it answers.
    result = asyncio.run(classifier.classify("إيه", question=question))

    assert result is AnswerKind.RED_FLAG
    system, user = captured["body"]["input"]
    assert "question" in system["content"].lower()
    assert question in user["content"]
    assert "إيه" in user["content"]


def test_classifier_offers_question_and_keeps_warning_signs_first() -> None:
    from hawlak_agent.classifier import OpenAIAnswerClassifier

    prompt = OpenAIAnswerClassifier._SYSTEM_PROMPT
    assert "question" in [member.value for member in AnswerKind]
    assert "Return question" in prompt
    assert "unless the reply also reports a warning sign" in prompt


def test_classifier_separates_noise_from_answers() -> None:
    prompt = OpenAIAnswerClassifier._SYSTEM_PROMPT

    assert "Return not_heard" in prompt
    assert "a reply in English is still an answer" in prompt
