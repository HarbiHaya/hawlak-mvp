from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import InboundMedia, ReviewOutcome, WorkflowEvent
from app.schemas.review_event import (
    PharmacistReviewRequested,
    ReviewOutcomeRequest,
)


class ReviewNotFoundError(RuntimeError):
    pass


class ReviewConflictError(RuntimeError):
    pass


class InvalidCursorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OutcomeResult:
    outcome: ReviewOutcome
    event: WorkflowEvent
    created: bool


class ReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_events(
        self, after: str | None, limit: int
    ) -> tuple[list[PharmacistReviewRequested], str | None]:
        sequence = _decode_cursor(after)
        rows = self.session.scalars(
            select(WorkflowEvent)
            .where(
                WorkflowEvent.event_type == "pharmacist_review_requested",
                WorkflowEvent.sequence > sequence,
                ~select(ReviewOutcome.id)
                .where(ReviewOutcome.workflow_event_sequence == WorkflowEvent.sequence)
                .exists(),
            )
            .order_by(WorkflowEvent.sequence)
            .limit(limit)
        ).all()
        data = [PharmacistReviewRequested.model_validate(row.payload) for row in rows]
        next_cursor = _encode_cursor(rows[-1].sequence) if rows else after
        return data, next_cursor

    def get_media(self, media_id: str) -> InboundMedia:
        media = self.session.get(InboundMedia, media_id)
        if media is None or media.processing_status != "stored" or not media.object_key:
            raise ReviewNotFoundError(media_id)
        return media

    def record_outcome(
        self,
        event_id: str,
        idempotency_key: str,
        body: ReviewOutcomeRequest,
    ) -> OutcomeResult:
        event = self.session.scalar(select(WorkflowEvent).where(WorkflowEvent.event_id == event_id))
        if event is None or event.event_type != "pharmacist_review_requested":
            raise ReviewNotFoundError(event_id)
        if event.event_version != body.event_version:
            raise ReviewConflictError("event_version_conflict")

        keyed = self.session.scalar(
            select(ReviewOutcome).where(ReviewOutcome.idempotency_key == idempotency_key)
        )
        if keyed is not None:
            if _same_outcome(keyed, event, body):
                return OutcomeResult(keyed, event, False)
            raise ReviewConflictError("idempotency_conflict")

        existing = self.session.scalar(
            select(ReviewOutcome).where(ReviewOutcome.workflow_event_sequence == event.sequence)
        )
        if existing is not None:
            raise ReviewConflictError("outcome_already_recorded")

        outcome = ReviewOutcome(
            workflow_event_sequence=event.sequence,
            outcome=body.outcome,
            reviewer_id=body.reviewer_id,
            note=body.note,
            idempotency_key=idempotency_key,
        )
        self.session.add(outcome)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ReviewConflictError("outcome_conflict") from exc
        return OutcomeResult(outcome, event, True)


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    prefix = "event-sequence:"
    if not cursor.startswith(prefix):
        raise InvalidCursorError(cursor)
    try:
        value = int(cursor.removeprefix(prefix))
    except ValueError as exc:
        raise InvalidCursorError(cursor) from exc
    if value < 0:
        raise InvalidCursorError(cursor)
    return value


def _encode_cursor(sequence: int) -> str:
    return f"event-sequence:{sequence}"


def _same_outcome(stored: ReviewOutcome, event: WorkflowEvent, body: ReviewOutcomeRequest) -> bool:
    return (
        stored.workflow_event_sequence == event.sequence
        and stored.outcome == body.outcome
        and stored.reviewer_id == body.reviewer_id
        and stored.note == body.note
    )
