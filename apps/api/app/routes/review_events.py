from typing import Annotated

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse, Response

from app.db import SessionDep
from app.schemas.review_event import (
    ReviewEventsPage,
    ReviewOutcomeRequest,
    ReviewOutcomeResponse,
)
from app.services.object_storage import ObjectStorageError, StorageDep
from app.services.review_service import (
    InvalidCursorError,
    ReviewConflictError,
    ReviewNotFoundError,
    ReviewService,
)

router = APIRouter()


@router.get("/review-events", response_model=ReviewEventsPage)
def list_review_events(
    session: SessionDep,
    after: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    try:
        data, next_cursor = ReviewService(session).list_events(after, limit)
    except InvalidCursorError:
        return JSONResponse(status_code=400, content={"error": "invalid_cursor"})
    return ReviewEventsPage(data=data, next_cursor=next_cursor)


@router.get("/media/{media_id}")
def get_review_media(media_id: str, session: SessionDep, storage: StorageDep):
    try:
        media = ReviewService(session).get_media(media_id)
        content = storage.get_bytes(media.object_key or "")
    except ReviewNotFoundError:
        return JSONResponse(status_code=404, content={"error": "media_not_found"})
    except ObjectStorageError:
        return JSONResponse(status_code=503, content={"error": "storage_unavailable"})
    return Response(content=content, media_type=media.mime_type)


@router.post(
    "/review-events/{event_id}/outcomes",
    response_model=ReviewOutcomeResponse,
    status_code=201,
)
def record_review_outcome(
    event_id: str,
    body: ReviewOutcomeRequest,
    session: SessionDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
):
    try:
        result = ReviewService(session).record_outcome(event_id, idempotency_key, body)
    except ReviewNotFoundError:
        return JSONResponse(status_code=404, content={"error": "review_event_not_found"})
    except ReviewConflictError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    payload = ReviewOutcomeResponse(
        data={
            "outcome_id": result.outcome.id,
            "event_id": result.event.event_id,
            "event_version": result.event.event_version,
            "outcome": result.outcome.outcome,
            "reviewer_id": result.outcome.reviewer_id,
            "note": result.outcome.note,
            "recorded_at": result.outcome.created_at,
        }
    )
    return JSONResponse(
        status_code=201 if result.created else 200,
        content=payload.model_dump(mode="json", by_alias=True),
    )
