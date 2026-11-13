from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApprovedQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    prompt: str

    @field_validator("id", "prompt")
    @classmethod
    def require_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("approved question fields cannot be blank")
        return value


class CallPlan(BaseModel):
    """Immutable content approved by an insurer reviewer before dispatch."""

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    id: str
    case_id: str = Field(alias="caseId")
    version: int = Field(gt=0)
    approved_at: str | None = Field(alias="approvedAt")
    phone_e164: str = Field(alias="phoneE164", pattern=r"^\+[1-9]\d{7,14}$")
    participant_label: str = Field(alias="participantLabel")
    language: str
    opening_script: str = Field(alias="openingScript")
    questions: tuple[ApprovedQuestion, ...]
    completion_script: str = Field(alias="completionScript")
    transfer_script: str = Field(alias="transferScript")
    responder_phone_e164: str = Field(alias="responderPhoneE164", pattern=r"^\+[1-9]\d{7,14}$")

    @field_validator(
        "id",
        "case_id",
        "participant_label",
        "language",
        "opening_script",
        "completion_script",
        "transfer_script",
    )
    @classmethod
    def require_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("call plan fields cannot be blank")
        return value

    @field_validator("questions")
    @classmethod
    def require_questions(cls, value: tuple[ApprovedQuestion, ...]) -> tuple[ApprovedQuestion, ...]:
        if not value:
            raise ValueError("call plan requires at least one approved question")
        if len({question.id for question in value}) != len(value):
            raise ValueError("approved question ids must be unique")
        return value


class AnswerKind(StrEnum):
    CLEAR = "clear"
    RED_FLAG = "red_flag"
    UNCERTAIN = "uncertain"
    TRANSFER_REQUEST = "transfer_request"


class CallActionKind(StrEnum):
    SPEAK = "speak"
    TRANSFER = "transfer"
    COMPLETE = "complete"


class CallAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: CallActionKind
    spoken_text: str
    question_id: str | None = None
    answer_kind: AnswerKind | None = None
    transfer_to: str | None = None


class CallConversation:
    """Deterministic state machine; it never creates patient-facing text."""

    def __init__(self, plan: CallPlan):
        if not plan.approved_at:
            raise ValueError("call plan is not approved")
        self._plan = plan
        self._question_index = -1
        self._started = False
        self._finished = False

    def start(self) -> CallAction:
        if self._started:
            raise RuntimeError("call conversation is already started")
        self._started = True
        return CallAction(kind=CallActionKind.SPEAK, spoken_text=self._plan.opening_script)

    @property
    def current_question(self) -> str | None:
        """The approved question now awaiting an answer."""
        if 0 <= self._question_index < len(self._plan.questions):
            return self._plan.questions[self._question_index].prompt
        return None

    def next_question(self) -> CallAction:
        self._ensure_active()
        self._question_index += 1
        if self._question_index >= len(self._plan.questions):
            self._finished = True
            return CallAction(
                kind=CallActionKind.COMPLETE,
                spoken_text=self._plan.completion_script,
            )
        question = self._plan.questions[self._question_index]
        return CallAction(
            kind=CallActionKind.SPEAK,
            spoken_text=question.prompt,
            question_id=question.id,
        )

    def record_answer(self, answer: AnswerKind) -> CallAction:
        self._ensure_active()
        if self._question_index < 0:
            raise RuntimeError("no approved question is awaiting an answer")
        if answer is not AnswerKind.CLEAR:
            self._finished = True
            question = self._plan.questions[self._question_index]
            return CallAction(
                kind=CallActionKind.TRANSFER,
                spoken_text=self._plan.transfer_script,
                question_id=question.id,
                answer_kind=answer,
                transfer_to=self._plan.responder_phone_e164,
            )
        return self.next_question()

    def _ensure_active(self) -> None:
        if not self._started:
            raise RuntimeError("call conversation is not started")
        if self._finished:
            raise RuntimeError("call conversation is finished")
